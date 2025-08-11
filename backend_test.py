#!/usr/bin/env python3
"""
Backend API Tests for Microcap Portfolio MVP
Tests all endpoints using the public frontend URL + /api prefix
"""

import requests
import json
import sys
from datetime import datetime
import time

class MicrocapAPITester:
    def __init__(self, base_url="https://107632a5-bcfe-46c3-9baa-85319f0745db.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.tests_run = 0
        self.tests_passed = 0
        self.session = requests.Session()
        self.session.timeout = 25  # Allow up to 25s per request as mentioned

    def log(self, message):
        """Log with timestamp"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, params=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}" if not endpoint.startswith('http') else endpoint
        headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        self.log(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = self.session.get(url, headers=headers, params=params)
            elif method == 'POST':
                response = self.session.post(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    self.log(f"   Response: {json.dumps(response_data, indent=2)}")
                    return True, response_data
                except:
                    self.log(f"   Response (text): {response.text[:200]}")
                    return True, response.text
            else:
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                self.log(f"   Response: {response.text[:300]}")
                return False, {}

        except Exception as e:
            self.log(f"❌ FAILED - Error: {str(e)}")
            return False, {}

    def test_health_check(self):
        """Test GET /api/health -> expect JSON contains {status: "ok"}"""
        success, response = self.run_test(
            "Health Check",
            "GET", 
            "health",
            200
        )
        if success and isinstance(response, dict) and response.get('status') == 'ok':
            self.log("✅ Health check contains status: ok")
            return True
        else:
            self.log("❌ Health check missing status: ok")
            return False

    def test_initial_portfolio(self):
        """Test GET /api/portfolio -> expect cash to equal 100.0 initially and positions length array"""
        success, response = self.run_test(
            "Initial Portfolio",
            "GET",
            "portfolio", 
            200
        )
        if success and isinstance(response, dict):
            cash = response.get('cash')
            positions = response.get('positions', [])
            
            if cash == 100.0:
                self.log("✅ Initial cash is 100.0")
            else:
                self.log(f"❌ Expected cash 100.0, got {cash}")
                
            if isinstance(positions, list):
                self.log(f"✅ Positions is array with length {len(positions)}")
                return cash == 100.0
            else:
                self.log("❌ Positions is not an array")
                return False
        return False

    def test_quote_fetch(self, ticker="RAVE"):
        """Test GET /api/quotes?ticker=RAVE -> expect ticker RAVE, currency USD, price present (number)"""
        success, response = self.run_test(
            f"Quote Fetch ({ticker})",
            "GET",
            "quotes",
            200,
            params={"ticker": ticker}
        )
        if success and isinstance(response, dict):
            ticker_match = response.get('ticker') == ticker.upper()
            currency_usd = response.get('currency') == 'USD'
            price_present = isinstance(response.get('price'), (int, float)) and response.get('price') is not None
            
            self.log(f"   Ticker: {response.get('ticker')} (expected {ticker.upper()})")
            self.log(f"   Currency: {response.get('currency')} (expected USD)")
            self.log(f"   Price: {response.get('price')} (type: {type(response.get('price'))})")
            
            if ticker_match and currency_usd and price_present:
                self.log("✅ Quote data valid")
                return True, response.get('price')
            else:
                self.log("❌ Quote data invalid")
                return False, None
        return False, None

    def test_place_trade(self, ticker="RAVE", side="buy", qty=1):
        """Test POST /api/trades/place -> expect 200 and response includes execution_price, ticker, side"""
        trade_data = {
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "order_type": "market"
        }
        
        success, response = self.run_test(
            f"Place Trade ({side.upper()} {qty} {ticker})",
            "POST",
            "trades/place",
            200,
            data=trade_data
        )
        
        if success and isinstance(response, dict):
            has_execution_price = 'execution_price' in response and isinstance(response['execution_price'], (int, float))
            ticker_match = response.get('ticker') == ticker.upper()
            side_match = response.get('side') == side
            
            self.log(f"   Execution Price: {response.get('execution_price')}")
            self.log(f"   Ticker: {response.get('ticker')} (expected {ticker.upper()})")
            self.log(f"   Side: {response.get('side')} (expected {side})")
            
            if has_execution_price and ticker_match and side_match:
                self.log("✅ Trade response valid")
                return True, response.get('execution_price')
            else:
                self.log("❌ Trade response invalid")
                return False, None
        return False, None

    def test_portfolio_after_trade(self, initial_cash=100.0, ticker="RAVE"):
        """Test GET /api/portfolio -> expect cash decreased (< 100), positions array includes RAVE with qty >=1"""
        success, response = self.run_test(
            "Portfolio After Trade",
            "GET",
            "portfolio",
            200
        )
        
        if success and isinstance(response, dict):
            cash = response.get('cash', 0)
            positions = response.get('positions', [])
            
            cash_decreased = cash < initial_cash
            self.log(f"   Cash: {cash} (was {initial_cash}, decreased: {cash_decreased})")
            
            # Check if RAVE position exists with qty >= 1
            rave_position = None
            for pos in positions:
                if pos.get('ticker') == ticker.upper():
                    rave_position = pos
                    break
            
            if rave_position:
                qty = rave_position.get('qty', 0)
                self.log(f"   {ticker} position found with qty: {qty}")
                qty_valid = qty >= 1
            else:
                self.log(f"   {ticker} position not found")
                qty_valid = False
            
            if cash_decreased and qty_valid:
                self.log("✅ Portfolio updated correctly after trade")
                return True
            else:
                self.log("❌ Portfolio not updated correctly")
                return False
        return False

    def test_research_summary(self, ticker="RAVE"):
        """Test POST /api/research/summary -> expect 200 with fields: ticker, summary (string), used_llm (boolean), sources (array)"""
        research_data = {"ticker": ticker}
        
        success, response = self.run_test(
            f"Research Summary ({ticker})",
            "POST",
            "research/summary",
            200,
            data=research_data
        )
        
        if success and isinstance(response, dict):
            ticker_match = response.get('ticker') == ticker.upper()
            summary_string = isinstance(response.get('summary'), str) and len(response.get('summary', '')) > 0
            used_llm_bool = isinstance(response.get('used_llm'), bool)
            sources_array = isinstance(response.get('sources'), list)
            
            self.log(f"   Ticker: {response.get('ticker')} (expected {ticker.upper()})")
            self.log(f"   Summary length: {len(response.get('summary', ''))}")
            self.log(f"   Used LLM: {response.get('used_llm')} (type: {type(response.get('used_llm'))})")
            self.log(f"   Sources count: {len(response.get('sources', []))}")
            
            if ticker_match and summary_string and used_llm_bool and sources_array:
                self.log("✅ Research summary response valid")
                return True
            else:
                self.log("❌ Research summary response invalid")
                return False
        return False

def main():
    """Run all backend API tests"""
    print("=" * 60)
    print("MICROCAP PORTFOLIO MVP - BACKEND API TESTS")
    print("=" * 60)
    
    tester = MicrocapAPITester()
    
    # Test sequence as requested
    tests_results = []
    
    # 1. Health check
    tester.log("🚀 Starting API tests...")
    result1 = tester.test_health_check()
    tests_results.append(("Health Check", result1))
    
    # 2. Initial portfolio
    result2 = tester.test_initial_portfolio()
    tests_results.append(("Initial Portfolio", result2))
    
    # 3. Quote fetch
    result3, price = tester.test_quote_fetch("RAVE")
    tests_results.append(("Quote Fetch", result3))
    
    # 4. Place trade
    result4, execution_price = tester.test_place_trade("RAVE", "buy", 1)
    tests_results.append(("Place Trade", result4))
    
    # 5. Portfolio after trade
    result5 = tester.test_portfolio_after_trade(100.0, "RAVE")
    tests_results.append(("Portfolio After Trade", result5))
    
    # 6. Research summary
    result6 = tester.test_research_summary("RAVE")
    tests_results.append(("Research Summary", result6))
    
    # Print final summary
    print("\n" + "=" * 60)
    print("FINAL TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in tests_results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    passed_count = sum(1 for _, passed in tests_results if passed)
    total_count = len(tests_results)
    
    print(f"\nOverall: {passed_count}/{total_count} tests passed")
    print(f"API Tests: {tester.tests_passed}/{tester.tests_run} individual requests successful")
    
    if passed_count == total_count:
        print("\n🎉 ALL BACKEND TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} BACKEND TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())