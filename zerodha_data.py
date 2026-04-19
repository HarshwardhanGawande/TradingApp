import requests
import json
import pandas as pd
from io import StringIO
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
import os
from urllib.parse import urlencode

try:
    import streamlit as st
except Exception:
    st = None

load_dotenv(override=True)

def cache_data_compat(*args, **kwargs):
    """Use Streamlit caching when available, otherwise return the function unchanged."""
    def decorator(func):
        if st is None:
            return func

        cache_api = getattr(st, "cache_data", None) or getattr(st, "cache", None)
        if cache_api is None:
            return func

        return cache_api(*args, **kwargs)(func)

    return decorator

nifty_dict = {
    "M&M": 519937,
    "ETERNAL": 1304833,
    "EICHERMOT": 232961,
    "SHRIRAMFIN": 1102337,
    "INDIGO": 2865921,
    "ADANIENT": 6401,
    "BAJFINANCE": 81153,
    "TMPV": 884737,
    "LT": 2939649,
    "TRENT": 502785,
    "BAJAJ-AUTO": 4267265,
    "HINDALCO": 348929,
    "TITAN": 897537,
    "SBIN": 779521,
    "TATASTEEL": 895745,
    "ADANIPORTS": 3861249,
    "JIOFIN": 4644609,
    "BAJAJFINSV": 4268801,
    "SUNPHARMA": 857857,
    "DRREDDY": 225537,
    "MARUTI": 2815745,
    "BHARTIARTL": 2714625,
    "APOLLOHOSP": 40193,
    "ICICIBANK": 1270529,
    "HINDUNILVR": 356865,
    "AXISBANK": 1510401,
    "RELIANCE": 738561,
    "KOTAKBANK": 492033,
    "JSWSTEEL": 3001089,
    "SBILIFE": 5582849,
    "ITC": 424961,
    "GRASIM": 315393,
    "MAXHEALTH": 5728513,
    "BEL": 98049,
    "HDFCBANK": 341249,
    "ASIANPAINT": 60417,
    "ULTRACEMCO": 2952193,
    "COALINDIA": 5215745,
    "POWERGRID": 3834113,
    "CIPLA": 177665,
    "HDFCLIFE": 119553,
    "WIPRO": 969473,
    "NTPC": 2977281,
    "TCS": 2953217,
    "TATACONSUM": 878593,
    "NESTLEIND": 4598529,
    "ONGC": 633601,
    "INFY": 408065,
    "TECHM": 3465729,
    "HCLTECH": 1850625,
    "NIFTY 50": 256265,
}

# ─── Config ──────────────────────────────────────────────────────────────────

USER_ID  = os.getenv('USER_ID')
PASSWORD = os.getenv('ZERODHA_PASSWORD')
ENCTOKEN = os.getenv('ENCTOKEN')

BASE_URL     = 'https://kite.zerodha.com'
LOGIN_URL    = f'{BASE_URL}/api/login'
TWOFA_URL    = f'{BASE_URL}/api/twofa'
HIST_URL     = f'{BASE_URL}/oms/instruments/historical/{{instrument_id}}/{{interval}}'
CHUNK_DAYS   = 1825   # 5-year max per request

s = requests.Session()

# ─── Auth ─────────────────────────────────────────────────────────────────────

def _get_headers():
    return {'authorization': f'enctoken {ENCTOKEN}'}


def _save_enctoken(enctoken: str):
    """Update only ENCTOKEN in .env, preserve all other lines."""
    env_lines = []
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            env_lines = f.readlines()

    env_lines = [l for l in env_lines if not l.startswith('ENCTOKEN=')]
    env_lines.append(f'ENCTOKEN={enctoken}\n')

    with open('.env', 'w') as f:
        f.writelines(env_lines)


def _login():
    """Perform login + 2FA and update ENCTOKEN globally."""
    global ENCTOKEN

    r = s.post(LOGIN_URL, data={'user_id': USER_ID, 'password': PASSWORD})
    request_id = r.json()['data']['request_id']

    twofa_value = input('Enter 2FA value: ')
    s.post(TWOFA_URL, data={
        'user_id': USER_ID,
        'request_id': request_id,
        'twofa_value': twofa_value,
    })

    ENCTOKEN = requests.utils.dict_from_cookiejar(s.cookies)['enctoken']
    print(f'New ENCTOKEN: {ENCTOKEN}')
    _save_enctoken(ENCTOKEN)


def test_validity():
    """Check token validity; re-login if expired."""
    print(f'Checking token: {ENCTOKEN}')

    resp = s.get(
        url=HIST_URL.format(instrument_id=86529, interval='minute'),
        headers=_get_headers(),
        params={'user_id': USER_ID, 'oi': '1',
                'from': '2026-03-25', 'to': '2026-03-25'},
    )

    if resp.status_code != 200:
        print(f"Token expired: {resp.json().get('message')} — logging in...")
        _login()
    else:
        print('Token valid.')

# ─── Data Fetching ────────────────────────────────────────────────────────────

def _fetch_chunk(tickers: list, from_str: str, to_str: str, interval: str) -> pd.DataFrame:
    """Fetch one date-range chunk for all tickers."""
    params = {'user_id': USER_ID, 'oi': '1', 'from': from_str, 'to': to_str}
    chunk_df = None

    for ticker in tickers:
        instrument_id = nifty_dict.get(ticker)
        if not instrument_id:
            raise ValueError(f'Unknown ticker: {ticker}')

        url  = HIST_URL.format(instrument_id=instrument_id, interval=interval)
        resp = s.get(url=url, headers=_get_headers(), params=params, verify=True)
        data = resp.json()

        print(f'{ticker} [{instrument_id}] — {data.get("status")} ({resp.status_code})')

        if data.get('status') != 'success':
            raise RuntimeError(f"Error fetching {ticker}: {data.get('message', 'Unknown error')}")

        df = (
            pd.DataFrame(data['data']['candles'])
              .iloc[:, [0, 4]]          # keep timestamp + close only
              .set_index(0)
              .rename(columns={4: ticker})
        )

        chunk_df = df if chunk_df is None else chunk_df.join(df)

    return chunk_df


def load_data(tickers: list, from_date: str, interval: str = 'day') -> pd.DataFrame:
    """
    Load historical close prices for given tickers.
    Automatically splits into 5-year chunks if range exceeds limit.
    """
    test_validity()

    from_dt  = datetime.strptime(from_date, '%Y-%m-%d').date()
    to_dt    = date.today()
    to_str   = to_dt.strftime('%Y-%m-%d')

    days_requested = (to_dt - from_dt).days
    main_df = None

    if days_requested > CHUNK_DAYS:
        current_from = from_dt
        while current_from < to_dt:
            chunk_to  = min(current_from + timedelta(days=CHUNK_DAYS), to_dt)
            print(f'Fetching chunk: {current_from} → {chunk_to}')
            chunk_df  = _fetch_chunk(tickers, current_from.strftime('%Y-%m-%d'),
                                     chunk_to.strftime('%Y-%m-%d'), interval)
            main_df   = chunk_df if main_df is None else pd.concat([main_df, chunk_df]).sort_index()
            current_from = chunk_to + timedelta(days=1)
    else:
        print(f'Fetching: {from_date} → {to_str}')
        main_df = _fetch_chunk(tickers, from_date, to_str, interval)

    main_df.index.name = 'Date'
    return main_df

@cache_data_compat(show_spinner=False, ttl=300)
def get_pre_open_data_cached(index):
    """
    Fetches pre-open market data for F&O from NSE India and returns as DataFrame.
    """
    print(f"Calling get_pre_open_data_cached() for index: {index}")
    url = "https://www.nseindia.com/api/market-data-pre-open"
    params = {'key': index}
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Referer': 'https://www.nseindia.com/',
    }

    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers)

    try:
        response = session.get(url, headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        # extract metadata
        metadata_list = [item["metadata"] for item in data["data"]]

        # convert to DataFrame
        df = pd.DataFrame(metadata_list)

        df = df[['symbol', 'pChange', 'totalTurnover', 'iep']]

        # Rename columns
        df.columns = ['SYMBOL', '%CHNG', 'VALUE', 'LTP']

        # 👉 REMOVE INDEX ROW HERE
        df = df[df['SYMBOL'] != index]

        # Convert to numeric
        df['%CHNG'] = pd.to_numeric(df['%CHNG'], errors='coerce')
        df['VALUE'] = pd.to_numeric(df['VALUE'], errors='coerce')
        df['LTP'] = pd.to_numeric(df['LTP'], errors='coerce')

        # Sort
        df = df.sort_values(by='VALUE', ascending=False).reset_index(drop=True)

        # Advance / Decline
        adv = df[df['%CHNG'] > 0]
        dec = df[df['%CHNG'] < 0]

        advance_turnover = adv['VALUE'].sum()
        decline_turnover = dec['VALUE'].sum()

        pct_adv_turnover = int(advance_turnover / decline_turnover * 100) if decline_turnover else 0
        pct_dec_turnover = 100 - pct_adv_turnover

        return df, len(adv), len(dec), pct_adv_turnover, pct_dec_turnover

    except Exception as e:
        print("Error:", e)
        return pd.DataFrame()

def get_live_nse_data(index):
    print("----------------------------------------------------------------")
    print(f"Fetching live data for index: {index}")


    url = "https://www.nseindia.com/api/equity-stockIndices"
    params = {'index': index}

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json',
        'Referer': 'https://www.nseindia.com/',
    }

    session = requests.Session()
    session.get("https://www.nseindia.com", headers=headers)

    try:
        response = session.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()

        df = pd.DataFrame(data['data'])

        # Keep only what you need
        df = df[['symbol', 'pChange', 'totalTradedValue', 'lastPrice']]

        # Rename columns
        df.columns = ['SYMBOL', '%CHNG', 'VALUE', 'LTP']

        # 👉 REMOVE INDEX ROW HERE
        df = df[df['SYMBOL'] != index]

        # Convert to numeric
        df['%CHNG'] = pd.to_numeric(df['%CHNG'], errors='coerce')
        df['VALUE'] = pd.to_numeric(df['VALUE'], errors='coerce')
        df['LTP'] = pd.to_numeric(df['LTP'], errors='coerce')

        # Sort
        df = df.sort_values(by='VALUE', ascending=False).reset_index(drop=True)

        # Advance / Decline
        adv = df[df['%CHNG'] > 0]
        dec = df[df['%CHNG'] < 0]

        advance_turnover = adv['VALUE'].sum()
        decline_turnover = dec['VALUE'].sum()

        pct_adv_turnover = int(advance_turnover / decline_turnover * 100) if decline_turnover else 0
        pct_dec_turnover = 100 - pct_adv_turnover

        return df, len(adv), len(dec), pct_adv_turnover, pct_dec_turnover

    except Exception as e:
        print("Error:", e)
        return pd.DataFrame()


