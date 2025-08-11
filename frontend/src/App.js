import { useEffect, useMemo, useState } from "react";
import "./App.css";
import axios from "axios";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import { Card } from "./components/ui/card";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Label } from "./components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/ui/select";
import { toast, Toaster } from "./components/ui/sonner";
import { TrendingUp, DollarSign, Newspaper, SendHorizonal, RefreshCw } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function StatCard({ icon: Icon, title, value, sub }) {
  return (
    <div className="card fade-in">
      <div className="flex items-center gap-3">
        <div className="badge"><Icon size={16} className="mr-1" />{title}</div>
      </div>
      <div className="mt-3 text-2xl font-extrabold">{value}</div>
      {sub && <div className="text-sm text-slate-400 mt-1">{sub}</div>}
    </div>
  );
}

function Section({ title, children, right }) {
  return (
    <div className="card fade-in">
      <div className="flex items-center justify-between mb-3">
        <div className="text-lg font-semibold">{title}</div>
        {right}
      </div>
      {children}
    </div>
  );
}

function App() {
  const [loading, setLoading] = useState(false);
  const [portfolio, setPortfolio] = useState(null);

  const [tkr, setTkr] = useState("");
  const [qty, setQty] = useState(1);
  const [side, setSide] = useState("buy");
  const [orderType, setOrderType] = useState("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");

  const [quote, setQuote] = useState(null);
  const [rsTicker, setRsTicker] = useState("");
  const [summary, setSummary] = useState(null);

  const fetchPortfolio = async () => {
    try {
      const { data } = await axios.get(`${API}/portfolio`);
      setPortfolio(data);
    } catch (e) {
      console.error(e);
      toast.error("Failed to load portfolio");
    }
  };

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const refreshQuote = async () => {
    if (!tkr) return;
    try {
      const { data } = await axios.get(`${API}/quotes`, { params: { ticker: tkr } });
      setQuote(data);
    } catch (e) {
      toast.error("Quote lookup failed");
    }
  };

  const placeTrade = async () => {
    if (!tkr || !qty) return toast.error("Ticker and quantity required");
    setLoading(true);
    try {
      const payload = {
        ticker: tkr.trim(),
        side,
        qty: Number(qty),
        order_type: orderType,
        limit_price: limitPrice ? Number(limitPrice) : null,
        stop_loss: stopLoss ? Number(stopLoss) : null,
        take_profit: takeProfit ? Number(takeProfit) : null,
      };
      const { data } = await axios.post(`${API}/trades/place`, payload);
      toast.success(`${data.side.toUpperCase()} ${data.qty} ${data.ticker} @ ${data.execution_price.toFixed(4)}`);
      setLimitPrice("");
      setStopLoss("");
      setTakeProfit("");
      setQuote(null);
      await fetchPortfolio();
    } catch (e) {
      const msg = e?.response?.data?.detail || "Trade failed";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const doSummarize = async () => {
    if (!rsTicker) return toast.error("Enter a ticker");
    setSummary({ loading: true });
    try {
      const { data } = await axios.post(`${API}/research/summary`, { ticker: rsTicker.trim() });
      setSummary(data);
    } catch (e) {
      setSummary(null);
      toast.error("Summary failed");
    }
  };

  return (
    <div className="app-shell text-slate-100">
      <Toaster richColors closeButton />
      <header className="header">
        <div className="container">
          <div className="flex items-center justify-between">
            <div>
              <div className="h1 text-2xl">Microcap Portfolio Agent</div>
              <div className="text-sm text-slate-400 mt-1">$100 account • US micro-caps only • Full shares only</div>
            </div>
            <a className="badge" href="https://emergent.sh" target="_blank" rel="noreferrer">Built on Emergent</a>
          </div>
        </div>
      </header>

      <main className="container">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
          <StatCard icon={DollarSign} title="Cash" value={portfolio ? `$${portfolio.cash.toFixed(2)}` : "—"} />
          <StatCard icon={TrendingUp} title="Equity" value={portfolio ? `$${portfolio.equity_value.toFixed(2)}` : "—"} />
          <StatCard icon={TrendingUp} title="Total" value={portfolio ? `$${portfolio.total_value.toFixed(2)}` : "—"} />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
          {/* Trade Builder */}
          <div className="lg:col-span-2">
            <Section
              title="Trade Builder"
              right={<Button className="btn" onClick={placeTrade} disabled={loading}>{loading ? "Placing…" : "Place Trade"}</Button>}
            >
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                <div className="col-span-2">
                  <Label className="label">Ticker</Label>
                  <div className="flex gap-2 items-center">
                    <Input placeholder="e.g. ABCD" value={tkr} onChange={e => setTkr(e.target.value.toUpperCase())} />
                    <Button variant="secondary" onClick={refreshQuote}><RefreshCw size={16} /></Button>
                  </div>
                </div>
                <div>
                  <Label className="label">Qty</Label>
                  <Input type="number" min={1} value={qty} onChange={e => setQty(e.target.value)} />
                </div>
                <div>
                  <Label className="label">Side</Label>
                  <Select value={side} onValueChange={setSide}>
                    <SelectTrigger><SelectValue placeholder="Side" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="buy">Buy</SelectItem>
                      <SelectItem value="sell">Sell</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label">Order</Label>
                  <Select value={orderType} onValueChange={setOrderType}>
                    <SelectTrigger><SelectValue placeholder="Order Type" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="market">Market</SelectItem>
                      <SelectItem value="limit">Limit</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="label">Limit</Label>
                  <Input type="number" step="0.0001" value={limitPrice} onChange={e => setLimitPrice(e.target.value)} placeholder="optional" />
                </div>
                <div>
                  <Label className="label">Stop</Label>
                  <Input type="number" step="0.0001" value={stopLoss} onChange={e => setStopLoss(e.target.value)} placeholder="optional" />
                </div>
                <div>
                  <Label className="label">Target</Label>
                  <Input type="number" step="0.0001" value={takeProfit} onChange={e => setTakeProfit(e.target.value)} placeholder="optional" />
                </div>
              </div>

              {quote && (
                <div className="mt-4 text-sm text-slate-300">
                  <div className="flex gap-4">
                    <div className="badge">{quote.ticker}</div>
                    <div>Price: <b>${quote.price ? quote.price.toFixed(4) : "—"}</b></div>
                    <div>Cap: <b>{quote.market_cap ? `$${(quote.market_cap/1e6).toFixed(1)}M` : "—"}</b></div>
                    <div>Currency: <b>{quote.currency || "—"}</b></div>
                  </div>
                </div>
              )}
            </Section>

            {/* Positions */}
            <Section title="Positions">
              <div className="overflow-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Qty</th>
                      <th>Avg</th>
                      <th>Last</th>
                      <th>Value</th>
                      <th>U/PnL</th>
                      <th>Stops/Targets</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio?.positions?.length ? portfolio.positions.map((p, idx) => (
                      <tr key={idx}>
                        <td className="font-semibold">{p.ticker}</td>
                        <td>{p.qty}</td>
                        <td>${p.avg_price.toFixed(4)}</td>
                        <td>${(p.last ?? 0).toFixed(4)}</td>
                        <td>${(p.value ?? 0).toFixed(2)}</td>
                        <td className={p.unrealized_pl &gt;= 0 ? "text-green-400" : "text-red-400"}>${(p.unrealized_pl ?? 0).toFixed(2)}</td>
                        <td className="text-slate-400 text-xs">SL: {p.stop_loss ?? '—'} | TP: {p.take_profit ?? '—'}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={7} className="text-slate-400">No positions yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Section>

            {/* Trades */}
            <Section title="Recent Trades">
              <div className="overflow-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Time (UTC)</th>
                      <th>Side</th>
                      <th>Ticker</th>
                      <th>Qty</th>
                      <th>Exec</th>
                      <th>Order</th>
                    </tr>
                  </thead>
                  <tbody>
                    {portfolio?.trades?.length ? portfolio.trades.map((t, i) => (
                      <tr key={i}>
                        <td>{new Date(t.timestamp).toISOString().replace('T', ' ').slice(0,16)}</td>
                        <td className={t.side === 'buy' ? 'text-green-400' : 'text-red-400'}>{t.side.toUpperCase()}</td>
                        <td>{t.ticker}</td>
                        <td>{t.qty}</td>
                        <td>${t.execution_price.toFixed(4)}</td>
                        <td>{t.order_type.toUpperCase()}</td>
                      </tr>
                    )) : (
                      <tr><td colSpan={6} className="text-slate-400">No trades yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>

          {/* Research */}
          <div className="lg:col-span-1">
            <Section title="Catalyst Scanner" right={<Button className="btn" onClick={doSummarize}><Newspaper size={16} className="mr-2" />Summarize</Button>}>
              <Label className="label">Ticker</Label>
              <div className="flex gap-2 items-center mb-3">
                <Input placeholder="e.g. ABCD" value={rsTicker} onChange={e => setRsTicker(e.target.value.toUpperCase())} />
              </div>
              <div className="text-xs text-slate-400 mb-2">Uses free Yahoo Finance news. If you provide EMERGENT_LLM_KEY in backend env, AI summaries will improve.</div>
              <div className="mt-2">
                {summary?.loading ? (
                  <div className="text-slate-400">Loading…</div>
                ) : summary ? (
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-400 mb-1">Summary</div>
                    <div className="text-sm leading-relaxed">{summary.summary}</div>
                    <div className="text-xs mt-2 text-slate-400">LLM used: {summary.used_llm ? 'Yes' : 'No (fallback)'} • Sources: {summary.sources?.length || 0}</div>
                  </div>
                ) : (
                  <div className="text-slate-500 text-sm">Enter a ticker and click Summarize to see catalysts.</div>
                )}
              </div>
            </Section>
          </div>
        </div>
      </main>

      <footer className="container mt-10 mb-8 text-slate-500 text-sm">
        Built for competitive micro-cap strategy. All prices via Yahoo (free, unofficial). Trade at your own risk.
      </footer>
    </div>
  );
}

export default App;