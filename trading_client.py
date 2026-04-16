"""
Zerodha Trading API Client
Supports order placement, position tracking, order management, authentication, margins, and holdings.
"""

import requests
import os
import pandas as pd
from typing import Literal, Optional, List, Dict
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Configuration ──────────────────────────────────────────────────────────

USER_ID = os.getenv('ZERODHA_USER_ID')
PASSWORD = os.getenv('ZERODHA_PASSWORD')
ENCTOKEN = os.getenv('ENCTOKEN')

BASE_URL = 'https://kite.zerodha.com'
LOGIN_URL = f'{BASE_URL}/api/login'
TWOFA_URL = f'{BASE_URL}/api/twofa'
HIST_URL = f'{BASE_URL}/oms/instruments/historical/{{instrument_id}}/{{interval}}'
ORDER_URL = f'{BASE_URL}/oms/orders'
POSITIONS_URL = f'{BASE_URL}/oms/portfolio/positions'
MARGINS_URL = f'{BASE_URL}/oms/user/margins'

# Path to your symbol token CSV – adjust if needed
TOKEN_CSV = r"C:\Users\harsh\Dropbox\Trading_2026\Latest_Dashboard\symbol_data\token_ids.csv"


# ─── Base Class ───────────────────────────────────────────────────────────────

class ZerodhaBase:
    _token_validated = False   # class-level flag to avoid repeated checks

    def __init__(self):
        global ENCTOKEN
        self.user_id = USER_ID
        self.password = PASSWORD
        self.enctoken = ENCTOKEN
        self.session = requests.Session()
        self._set_headers()

    def _set_headers(self):
        self.session.headers.update({
            'authorization': f'enctoken {self.enctoken}',
            'Content-Type': 'application/x-www-form-urlencoded',
        })

    def _save_enctoken(self, enctoken: str):
        try:
            env_lines = []
            env_file = '.env'
            if os.path.exists(env_file):
                with open(env_file, 'r') as f:
                    env_lines = f.readlines()
            env_lines = [l for l in env_lines if not l.startswith('ENCTOKEN=')]
            env_lines.append(f'ENCTOKEN={enctoken}\n')
            with open(env_file, 'w') as f:
                f.writelines(env_lines)
            print(f'✓ ENCTOKEN saved to .env file')
        except Exception as e:
            print(f'⚠ Warning: Could not save enctoken: {e}')

    def _validate_token(self, token: str) -> bool:
        """Test if a given token is valid by calling a simple API."""
        test_session = requests.Session()
        test_session.headers.update({'authorization': f'enctoken {token}'})
        try:
            resp = test_session.get(
                url=HIST_URL.format(instrument_id=86529, interval='minute'),
                params={'user_id': self.user_id, 'oi': '1',
                        'from': '2026-03-25', 'to': '2026-03-25'},
                timeout=10
            )
            return resp.status_code == 200
        except:
            return False

    def _login(self):
        global ENCTOKEN
        print("\n" + "="*50)
        print("LOGIN REQUIRED - Token expired or invalid")
        print("="*50)

        # --- Step 0: Ask for existing token (optional) ---
        print("\n💡 If you have an existing ENCTOKEN from another session, paste it here and press Enter.")
        print("   Otherwise, just press Enter to continue with normal login (password + 2FA).")
        existing_token = input("Paste ENCTOKEN (or press Enter): ").strip()

        if existing_token:
            print("🔍 Validating provided token...")
            if self._validate_token(existing_token):
                print("✓ Token is valid. Saving to .env and continuing...")
                self.enctoken = existing_token
                ENCTOKEN = existing_token
                self._save_enctoken(existing_token)
                self._set_headers()
                ZerodhaBase._token_validated = True
                print("✓ Login completed using provided token.")
                print("="*50 + "\n")
                return
            else:
                print("❌ Provided token is invalid. Falling back to normal login.\n")

        # --- Normal login with password and 2FA ---
        print(f"Logging in as: {self.user_id}")
        r = self.session.post(LOGIN_URL, data={
            'user_id': self.user_id,
            'password': self.password,
        })
        if r.status_code != 200:
            print(f"❌ Login failed! Status: {r.status_code}")
            print(f"Response: {r.text}")
            raise Exception(f"Login failed: {r.text}")
        response_data = r.json()
        if response_data.get('status') != 'success':
            print(f"❌ Login failed: {response_data.get('message', 'Unknown error')}")
            raise Exception(f"Login failed: {response_data.get('message')}")
        request_id = response_data['data']['request_id']
        print(f"✓ Login step 1 successful. Request ID: {request_id}")
        print("\n" + "-"*30)
        twofa_value = input("Enter 2FA value (from SMS/App): ").strip()
        print("-"*30)
        twofa_response = self.session.post(TWOFA_URL, data={
            'user_id': self.user_id,
            'request_id': request_id,
            'twofa_value': twofa_value,
        })
        if twofa_response.status_code != 200:
            print(f"❌ 2FA verification failed! Status: {twofa_response.status_code}")
            print(f"Response: {twofa_response.text}")
            raise Exception(f"2FA failed: {twofa_response.text}")
        twofa_data = twofa_response.json()
        if twofa_data.get('status') != 'success':
            print(f"❌ 2FA verification failed: {twofa_data.get('message')}")
            raise Exception(f"2FA failed: {twofa_data.get('message')}")
        cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
        if 'enctoken' not in cookies_dict:
            print(f"❌ No enctoken found in cookies. Available cookies: {list(cookies_dict.keys())}")
            raise Exception("Could not extract enctoken after login")
        self.enctoken = cookies_dict['enctoken']
        ENCTOKEN = self.enctoken
        print(f"✓ New ENCTOKEN generated: {self.enctoken[:20]}...")
        self._save_enctoken(self.enctoken)
        self._set_headers()
        ZerodhaBase._token_validated = True
        print("✓ Login completed successfully!")
        print("="*50 + "\n")

    def test_validity(self):
        """Check token validity only once per process."""
        if ZerodhaBase._token_validated:
            return True

        if not self.enctoken:
            print("⚠ No enctoken found. Logging in...")
            self._login()
            ZerodhaBase._token_validated = True
            return True

        print(f'🔍 Checking token validity...')
        try:
            resp = self.session.get(
                url=HIST_URL.format(instrument_id=86529, interval='minute'),
                params={'user_id': self.user_id, 'oi': '1',
                        'from': '2026-03-25', 'to': '2026-03-25'},
                timeout=10
            )
            if resp.status_code == 200:
                print('✓ Token is valid.')
                ZerodhaBase._token_validated = True
                return True
            else:
                error_msg = resp.json().get('message', 'Unknown error') if resp.text else 'No response'
                print(f"⚠ Token expired/invalid: {error_msg}")
                print("🔄 Logging in...")
                self._login()
                ZerodhaBase._token_validated = True
                return True
        except Exception as e:
            print(f"⚠ Token validation error: {e}")
            print("🔄 Attempting login...")
            self._login()
            ZerodhaBase._token_validated = True
            return True


# ─── Order Manager ───────────────────────────────────────────────────────────

class OrderManager(ZerodhaBase):
    def __init__(self):
        super().__init__()
        self.test_validity()

    def _fetch_orders(self, order_id: Optional[str] = None) -> Dict:
        url = f"{ORDER_URL}/{order_id}" if order_id else ORDER_URL
        response = self.session.get(url, params={'user_id': self.user_id})
        response.raise_for_status()
        return response.json()

    def get_all_orders(self) -> List[Dict]:
        data = self._fetch_orders()
        return data.get('data', [])

    def get_open_orders(self) -> pd.DataFrame:
        orders = self.get_all_orders()
        open_statuses = ['OPEN', 'TRIGGER PENDING', 'PENDING', 'AMO REQ RECEIVED']
        open_orders = [o for o in orders if o.get('status') in open_statuses]
        if not open_orders:
            return pd.DataFrame(columns=['Time', 'Type', 'Instrument', 'Product', 'Qty', 'LTP', 'Price', 'Status'])
        rows = []
        for o in open_orders:
            ts = o.get('order_timestamp', '')
            time_str = ts.split()[1] if ' ' in ts else ts[:8]
            trans_type = o.get('transaction_type', '')
            instrument = f"{o.get('tradingsymbol', '')} {o.get('exchange', '')}".strip()
            product = o.get('product', '')
            filled = o.get('filled_quantity', 0)
            qty = o.get('quantity', 0)
            qty_str = f"{filled} / {qty}"
            price_val = o.get('price', 0)
            ltp = price_val
            status = o.get('status', '')
            rows.append({
                'Time': time_str, 'Type': trans_type, 'Instrument': instrument,
                'Product': product, 'Qty': qty_str, 'LTP': ltp,
                'Price': price_val, 'Status': status
            })
        df = pd.DataFrame(rows)
        df = df.sort_values('Time', ascending=False).reset_index(drop=True)
        return df

    def cancel_order(self, order_id: str, variety: str = 'regular', parent_order_id: Optional[str] = None) -> Dict:
        url = f"{ORDER_URL}/{variety}/{order_id}"
        params = {'order_id': order_id, 'variety': variety, 'user_id': self.user_id}
        if parent_order_id:
            params['parent_order_id'] = parent_order_id
        response = self.session.delete(url, params=params)
        response.raise_for_status()
        return response.json()


# ─── Position Manager ────────────────────────────────────────────────────────

class PositionManager(ZerodhaBase):
    def __init__(self):
        super().__init__()
        self.test_validity()

    def get_net_positions(self) -> List[Dict]:
        response = self.session.get(POSITIONS_URL, params={'user_id': self.user_id})
        response.raise_for_status()
        data = response.json()
        return data.get('data', {}).get('net', [])

    def get_total_pnl(self) -> float:
        positions = self.get_net_positions()
        return sum(p.get('pnl', 0) for p in positions)


# ─── Holdings Manager ────────────────────────────────────────────────────────

class HoldingsManager(ZerodhaBase):
    HOLDINGS_URL = f'{BASE_URL}/oms/portfolio/holdings'

    def __init__(self):
        super().__init__()
        self.test_validity()

    def get_holdings(self) -> List[Dict]:
        response = self.session.get(self.HOLDINGS_URL, params={'user_id': self.user_id})
        response.raise_for_status()
        data = response.json()
        return data.get('data', [])

    def get_holdings_dataframe(self) -> pd.DataFrame:
        holdings = self.get_holdings()
        if not holdings:
            return pd.DataFrame(columns=['Instrument', 'Qty.', 'Avg. cost', 'LTP', 'Invested', 'Cur. val', 'P&L', 'Net chg.', 'Day chg.'])
        rows = []
        for h in holdings:
            symbol = h.get('tradingsymbol', '')
            qty = h.get('quantity', 0)
            avg_cost = h.get('average_price', 0.0)
            ltp = h.get('last_price', 0.0)
            invested = avg_cost * qty
            cur_val = ltp * qty
            pnl = h.get('pnl', 0.0)
            net_chg_percent = (pnl / invested * 100) if invested != 0 else 0.0
            day_chg_percent = h.get('day_change_percentage', 0.0)
            rows.append({
                'Instrument': symbol, 'Qty.': qty, 'Avg. cost': round(avg_cost, 2),
                'LTP': round(ltp, 2), 'Invested': round(invested, 2), 'Cur. val': round(cur_val, 2),
                'P&L': round(pnl, 2), 'Net chg.': f"{net_chg_percent:+.2f}%", 'Day chg.': f"{day_chg_percent:+.2f}%"
            })
        return pd.DataFrame(rows)

    def get_holdings_summary(self) -> tuple:
        holdings = self.get_holdings()
        total_day_pnl = sum(h.get('day_change', 0.0) * h.get('quantity', 0) for h in holdings)
        total_pnl = sum(h.get('pnl', 0.0) for h in holdings)
        return total_day_pnl, total_pnl


# ─── Margins Manager ─────────────────────────────────────────────────────────

class MarginsManager(ZerodhaBase):
    def __init__(self):
        super().__init__()
        self.test_validity()

    def get_margin_summary(self) -> Dict:
        response = self.session.get(f"{MARGINS_URL}/equity", params={'user_id': self.user_id})
        response.raise_for_status()
        data = response.json().get('data', {})
        available = data.get('available', {})
        utilised = data.get('utilised', {})
        return {
            'available_margin': data.get('net', 0.0),
            'used_margin': sum(utilised.values()),
            'available_cash': available.get('cash', 0.0),
        }


# ─── Intraday Trading (Order Placement) ──────────────────────────────────────

class ZerodhaIntraday(ZerodhaBase):
    ORDER_URL = f'{BASE_URL}/oms/orders'

    def __init__(self):
        super().__init__()
        self.test_validity()

    def _place_order(self, variety: str, payload: dict) -> dict:
        """Place order, return dict with 'status' and 'data' or 'message'."""
        if self.user_id:
            payload['user_id'] = self.user_id
        print(f"DEBUG: Sending order to {self.ORDER_URL}/{variety}")
        print(f"DEBUG: Payload = {payload}")
        try:
            response = self.session.post(f'{self.ORDER_URL}/{variety}', data=payload)
            print(f"DEBUG: Response status = {response.status_code}")
            print(f"DEBUG: Response text = {response.text}")
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Return a structured error dict
            error_msg = str(e)
            try:
                error_json = response.json()
                error_msg = error_json.get('message', error_json.get('error', str(e)))
            except:
                pass
            return {"status": "error", "message": error_msg, "data": None}

    def _base_payload(self, tradingsymbol, exchange, transaction_type, quantity):
        return {
            'exchange': exchange,
            'tradingsymbol': tradingsymbol,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'product': 'MIS',      # Base product, can be overridden
            'validity': 'DAY',
            'tag': 'tfc_tv',
        }

    def market(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
               quantity: int, exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'regular', 'order_type': 'MARKET',
            'price': 0, 'trigger_price': 0, 'disclosed_quantity': 0,
            'squareoff': 0, 'stoploss': 0, 'trailing_stoploss': 0,
        })
        return self._place_order('regular', payload)

    def limit(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
              quantity: int, price: float, exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'regular', 'order_type': 'LIMIT',
            'price': price, 'trigger_price': 0, 'disclosed_quantity': 0,
            'squareoff': 0, 'stoploss': 0, 'trailing_stoploss': 0,
        })
        return self._place_order('regular', payload)

    def cover_market(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
                    quantity: int, trigger_price: float, exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'co',
            'order_type': 'MARKET',
            'trigger_price': trigger_price,
            'product': 'CO'               # <-- COVER ORDERS REQUIRE PRODUCT 'CO'
        })
        # Remove the 'price' key if it exists, as it's not allowed for MARKET orders
        payload.pop('price', None)
        # Ensure other keys not used by CO are removed or set correctly
        return self._place_order('co', payload)

    def cover_limit(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
                    quantity: int, price: float, trigger_price: float,
                    exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'co', 'order_type': 'LIMIT',
            'price': price, 'trigger_price': trigger_price,
            'product': 'CO'      # FIXED: required for cover orders
        })
        return self._place_order('co', payload)

    def amo_market(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
                   quantity: int, exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'amo', 'order_type': 'MARKET',
            'price': 0, 'trigger_price': 0, 'disclosed_quantity': 0,
        })
        return self._place_order('amo', payload)

    def amo_limit(self, tradingsymbol: str, transaction_type: Literal['BUY', 'SELL'],
                  quantity: int, price: float, exchange: str = 'NSE') -> dict:
        payload = self._base_payload(tradingsymbol, exchange, transaction_type, quantity)
        payload.update({
            'variety': 'amo', 'order_type': 'LIMIT',
            'price': price, 'trigger_price': 0, 'disclosed_quantity': 0,
        })
        return self._place_order('amo', payload)


# ─── Unified Trading Client ──────────────────────────────────────────────────

class ZerodhaClient:
    def __init__(self):
        self.trading = ZerodhaIntraday()
        self.orders = OrderManager()
        self.positions = PositionManager()
        self.holdings = HoldingsManager()
        self.margins = MarginsManager()
        self.symbols, self.token_map = self.load_symbols()

    @staticmethod
    def load_symbols():
        if not os.path.exists(TOKEN_CSV):
            raise FileNotFoundError(f"Token CSV not found: {TOKEN_CSV}")
        df = pd.read_csv(TOKEN_CSV, dtype={"symbol": str, "token": int})
        df.columns = df.columns.str.strip().str.lower()
        token_dict = dict(zip(df["symbol"], df["token"]))
        return sorted(df["symbol"].tolist()), token_dict

    def fetch_ltp(self, symbol: str):
        token = self.token_map.get(symbol)
        if not token:
            return None, f"No token for {symbol}"
        today = datetime.now().date()
        from_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        try:
            resp = self.trading.session.get(
                HIST_URL.format(instrument_id=token, interval="minute"),
                params={"user_id": self.trading.user_id, "oi": "1",
                        "from": from_date, "to": to_date}
            )
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"
            candles = resp.json().get("data", {}).get("candles", [])
            if not candles:
                return None, "No candles"
            ltp = float(candles[-1][4])
            return ltp, None
        except Exception as e:
            return None, str(e)

    def fetch_ohlcv(self, symbol: str):
        token = self.token_map.get(symbol)
        if not token:
            return None, f"No token for {symbol}"
        today = datetime.now().date()
        from_date = (today - timedelta(days=10)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        try:
            resp = self.trading.session.get(
                HIST_URL.format(instrument_id=token, interval="minute"),
                params={"user_id": self.trading.user_id, "oi": "1",
                        "from": from_date, "to": to_date}
            )
            if resp.status_code != 200:
                return None, f"HTTP {resp.status_code}"
            candles = resp.json().get("data", {}).get("candles", [])
            if not candles:
                return None, "No candles"
            last_date = candles[-1][0][:10]
            day_candles = [c for c in candles if c[0][:10] == last_date]
            if not day_candles:
                return None, "No candles for last day"
            open_price = float(day_candles[0][1])
            high_price = max(float(c[2]) for c in day_candles)
            low_price = min(float(c[3]) for c in day_candles)
            close_price = float(day_candles[-1][4])
            volume = sum(int(c[5]) for c in day_candles)
            prev_candles = [c for c in candles if c[0][:10] < last_date]
            if prev_candles:
                prev_date = prev_candles[-1][0][:10]
                prev_day = [c for c in prev_candles if c[0][:10] == prev_date]
                prev_close = float(prev_day[-1][4]) if prev_day else open_price
            else:
                prev_close = open_price
            pct_change = ((close_price - prev_close) / prev_close) * 100
            return {
                "date": last_date, "open": open_price, "high": high_price, "low": low_price,
                "close": close_price, "volume": volume, "prev_close": prev_close, "pct_change": pct_change
            }, None
        except Exception as e:
            return None, str(e)

    # Shortcuts
    def get_open_orders(self):
        return self.orders.get_open_orders()

    def get_holdings_df(self):
        return self.holdings.get_holdings_dataframe()

    def get_holdings_summary(self):
        return self.holdings.get_holdings_summary()

    def get_holdings(self):
        return self.holdings.get_holdings()

    def get_margin_summary(self):
        return self.margins.get_margin_summary()

    def amo_market(self, symbol, transaction_type, quantity, exchange='NSE'):
        return self.trading.amo_market(symbol, transaction_type, quantity, exchange)

    def amo_limit(self, symbol, transaction_type, quantity, price, exchange='NSE'):
        return self.trading.amo_limit(symbol, transaction_type, quantity, price, exchange)

    def buy_market(self, symbol, quantity, exchange='NSE'):
        return self.trading.market(symbol, 'BUY', quantity, exchange)

    def sell_market(self, symbol, quantity, exchange='NSE'):
        return self.trading.market(symbol, 'SELL', quantity, exchange)