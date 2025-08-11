from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import asyncio

# External deps
import httpx
import yfinance as yf

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("microcap-portfolio")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# =======================
# Models
# =======================
class Position(BaseModel):
    ticker: str
    qty: int
    avg_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class TradeRequest(BaseModel):
    ticker: str
    side: str  # 'buy' | 'sell'
    qty: int = Field(gt=0)
    order_type: str = Field(default="market")  # 'market' | 'limit'
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    @validator('side')
    def validate_side(cls, v):
        if v not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @validator('order_type')
    def validate_order_type(cls, v):
        if v not in {"market", "limit"}:
            raise ValueError("order_type must be 'market' or 'limit'")
        return v

class Trade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    portfolio_id: str
    ticker: str
    side: str
    qty: int
    order_type: str
    requested_limit: Optional[float] = None
    execution_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "filled"

class Portfolio(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    cash: float = 100.0

class PortfolioView(BaseModel):
    id: str
    cash: float
    equity_value: float
    total_value: float
    positions: List[Dict[str, Any]]
    trades: List[Trade]

class Quote(BaseModel):
    ticker: str
    price: Optional[float]
    currency: Optional[str]
    market_cap: Optional[float]
    name: Optional[str]
    exchange: Optional[str]

class ResearchSummaryRequest(BaseModel):
    ticker: str

class ResearchSummaryResponse(BaseModel):
    ticker: str
    summary: str
    used_llm: bool
    sources: List[Dict[str, Any]]

# =======================
# Utilities
# =======================
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

async def fetch_quote(ticker: str) -> Quote:
    t = yf.Ticker(ticker)
    price = None
    currency = None
    mc = None
    name = None
    exchange = None

    # Try fast_info first
    try:
        fi = t.fast_info
        price = float(fi.get('last_price')) if fi.get('last_price') else None
        mc = float(fi.get('market_cap')) if fi.get('market_cap') else None
        currency = fi.get('currency')
    except Exception:
        pass

    # Fallback to info
    if price is None or mc is None or currency is None:
        try:
            info = t.info
            price = price or info.get('regularMarketPrice')
            mc = mc or info.get('marketCap')
            currency = currency or info.get('currency')
            name = info.get('shortName') or info.get('longName')
            exchange = info.get('exchange') or info.get('fullExchangeName')
        except Exception:
            # Ultimate fallback via 1d history
            try:
                hist = t.history(period="1d", interval="1m")
                if not hist.empty:
                    price = float(hist['Close'].iloc[-1])
            except Exception:
                pass

    return Quote(ticker=ticker.upper(), price=price, currency=currency, market_cap=mc, name=name, exchange=exchange)

async def validate_microcap_us(ticker: str) -> None:
    q = await fetch_quote(ticker)
    if q.market_cap is None:
        raise HTTPException(status_code=400, detail="Unable to determine market cap for ticker")
    if q.market_cap >= 300_000_000:
        raise HTTPException(status_code=400, detail="Only micro-caps (market cap < $300M) are allowed")
    # Basic US listing proxy: USD currency
    if (q.currency or "").upper() != "USD":
        raise HTTPException(status_code=400, detail="Only US-listed (USD) tickers are allowed")

async def get_or_create_portfolio() -> Portfolio:
    doc = await db.portfolios.find_one({})
    if doc:
        return Portfolio(**{k: doc[k] for k in ['id', 'created_at', 'cash']})
    p = Portfolio()
    await db.portfolios.insert_one({"_id": p.id, **p.dict()})
    # Initialize positions/trades collections
    await db.positions.create_index([("ticker", 1)], background=True)
    await db.trades.create_index([("portfolio_id", 1), ("timestamp", -1)], background=True)
    return p

async def get_positions_map() -> Dict[str, Position]:
    cursor = db.positions.find({})
    items = await cursor.to_list(length=1000)
    out: Dict[str, Position] = {}
    for it in items:
        out[it['ticker']] = Position(**{k: it.get(k) for k in ['ticker', 'qty', 'avg_price', 'stop_loss', 'take_profit']})
    return out

async def upsert_position(pos: Position) -> None:
    await db.positions.update_one(
        {"ticker": pos.ticker},
        {"$set": {**pos.dict()}},
        upsert=True,
    )

async def remove_position(ticker: str) -> None:
    await db.positions.delete_one({"ticker": ticker})

# =======================
# LLM Summarization (Emergent Integrations via httpx)
# =======================
async def summarize_text_llm(text: str, max_length: int = 180) -> Optional[str]:
    if not EMERGENT_LLM_KEY:
        return None
    base_url = "https://api.emergentintegrations.com"
    payload = {
        "text": text,
        "operation": "summarize",
        "parameters": {"max_length": max_length, "language": "en", "style": "professional"},
    }
    headers = {
        "Authorization": f"Bearer {EMERGENT_LLM_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Microcap-Portfolio/1.0",
    }
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=5.0)

    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout) as hc:
            resp = await hc.post(f"{base_url}/v1/summarize", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('summary') or data.get('result')
            logger.warning(f"LLM summarize failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"LLM error: {e}")
    return None

# Simple fallback extractive summary
def fallback_summary(text: str, max_chars: int = 500) -> str:
    text = (text or '').replace('\n', ' ')
    if len(text) <= max_chars:
        return text
    # pick first sentences up to limit
    parts = [p.strip() for p in text.split('. ') if len(p.strip()) > 20]
    out = []
    total = 0
    for s in parts:
        s2 = s if s.endswith('.') else s + '.'
        if total + len(s2) > max_chars:
            break
        out.append(s2)
        total += len(s2)
    if not out:
        return text[: max_chars - 3] + '...'
    return ' '.join(out)

# =======================
# Routes
# =======================
@api.get("/")
async def root():
    return {"message": "Microcap Portfolio API ready"}

@api.get("/health")
async def health():
    return {"status": "ok", "mongo": bool(client), "llm_configured": bool(EMERGENT_LLM_KEY)}

@api.get("/quotes", response_model=Quote)
async def api_quotes(ticker: str):
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker required")
    return await fetch_quote(ticker)

@api.get("/portfolio", response_model=PortfolioView)
async def api_portfolio():
    p = await get_or_create_portfolio()
    positions = await get_positions_map()

    # Fetch live prices sequentially (small universe) for MVP
    equity_value = 0.0
    positions_list: List[Dict[str, Any]] = []
    for tck, pos in positions.items():
        q = await fetch_quote(tck)
        last = q.price or 0.0
        value = last * pos.qty
        pl = (last - pos.avg_price) * pos.qty
        equity_value += value
        positions_list.append({
            "ticker": tck,
            "qty": pos.qty,
            "avg_price": pos.avg_price,
            "last": last,
            "value": value,
            "unrealized_pl": pl,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
        })

    total_value = p.cash + equity_value
    trades_docs = await db.trades.find({}).sort("timestamp", -1).limit(50).to_list(50)
    trades: List[Trade] = [
        Trade(**{k: td[k] for k in [
            'id','portfolio_id','ticker','side','qty','order_type','requested_limit','execution_price','stop_loss','take_profit','timestamp','status'
        ]}) for td in trades_docs
    ]

    return PortfolioView(
        id=p.id,
        cash=round(p.cash, 4),
        equity_value=round(equity_value, 4),
        total_value=round(total_value, 4),
        positions=positions_list,
        trades=trades,
    )

@api.post("/trades/place", response_model=Trade)
async def place_trade(req: TradeRequest):
    ticker = req.ticker.upper().strip()
    await validate_microcap_us(ticker)

    p = await get_or_create_portfolio()
    pos_map = await get_positions_map()

    # Determine executable price
    q = await fetch_quote(ticker)
    if not q.price:
        raise HTTPException(status_code=400, detail="No live price available for execution")

    exec_price = float(q.price)
    if req.order_type == 'limit':
        if req.side == 'buy' and req.limit_price is not None and exec_price > req.limit_price:
            raise HTTPException(status_code=400, detail="Limit buy not filled at current price")
        if req.side == 'sell' and req.limit_price is not None and exec_price < req.limit_price:
            raise HTTPException(status_code=400, detail="Limit sell not filled at current price")

    if req.side == 'buy':
        cost = exec_price * req.qty
        if cost > p.cash + 1e-9:
            raise HTTPException(status_code=400, detail="Insufficient cash")
        # Update cash
        p.cash -= cost
        await db.portfolios.update_one({"_id": p.id}, {"$set": {"cash": p.cash}})
        # Update/insert position
        if ticker in pos_map:
            old = pos_map[ticker]
            new_qty = old.qty + req.qty
            new_avg = (old.avg_price * old.qty + exec_price * req.qty) / new_qty
            pos = Position(ticker=ticker, qty=new_qty, avg_price=new_avg, stop_loss=req.stop_loss or old.stop_loss, take_profit=req.take_profit or old.take_profit)
        else:
            pos = Position(ticker=ticker, qty=req.qty, avg_price=exec_price, stop_loss=req.stop_loss, take_profit=req.take_profit)
        await upsert_position(pos)
    else:  # sell
        if ticker not in pos_map or pos_map[ticker].qty < req.qty:
            raise HTTPException(status_code=400, detail="Insufficient shares to sell")
        proceeds = exec_price * req.qty
        p.cash += proceeds
        await db.portfolios.update_one({"_id": p.id}, {"$set": {"cash": p.cash}})
        # Reduce position
        old = pos_map[ticker]
        new_qty = old.qty - req.qty
        if new_qty == 0:
            await remove_position(ticker)
        else:
            pos = Position(ticker=ticker, qty=new_qty, avg_price=old.avg_price, stop_loss=old.stop_loss, take_profit=old.take_profit)
            await upsert_position(pos)

    trade = Trade(
        portfolio_id=p.id,
        ticker=ticker,
        side=req.side,
        qty=req.qty,
        order_type=req.order_type,
        requested_limit=req.limit_price,
        execution_price=exec_price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
    )
    await db.trades.insert_one({"_id": trade.id, **trade.dict()})
    return trade

@api.post("/research/summary", response_model=ResearchSummaryResponse)
async def research_summary(body: ResearchSummaryRequest):
    ticker = body.ticker.upper().strip()
    t = yf.Ticker(ticker)
    sources: List[Dict[str, Any]] = []
    combined_text = ""

    # Try Yahoo Finance news via yfinance
    try:
        news = t.news or []  # list of dicts
        for item in news[:5]:
            title = item.get('title')
            publisher = item.get('publisher')
            link = item.get('link')
            desc = item.get('summary') or item.get('content') or ''
            sources.append({"title": title, "publisher": publisher, "link": link})
            combined_text += f"{title}. {desc}\n"
    except Exception:
        pass

    if not combined_text:
        # Fallback to company info
        try:
            info = t.info
            desc = info.get('longBusinessSummary') or ''
            combined_text = f"Company Overview: {desc}"
            sources.append({"title": "Company Overview", "publisher": "Yahoo Finance", "link": None})
        except Exception:
            combined_text = f"No news available for {ticker}."

    # Call LLM if key present, else fallback
    summary = await summarize_text_llm(combined_text, max_length=180)
    used_llm = summary is not None
    if not used_llm:
        summary = fallback_summary(combined_text, max_chars=500)

    return ResearchSummaryResponse(ticker=ticker, summary=summary, used_llm=used_llm, sources=sources)

# Include router
app.include_router(api)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()