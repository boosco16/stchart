"""
QULLAMAGGIE 5-STAR SETUP SCANNER
Runs via GitHub Actions twice daily, writes results to Supabase.
"""

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ['YF_NO_CACHE'] = '1'

import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

import yfinance as yf
yf.set_tz_cache_location("/tmp/yf_cache")
import pandas as pd
import numpy as np
import requests
import warnings
import time
import math
import multiprocessing
import concurrent.futures
from datetime import datetime, timedelta
from supabase import create_client

warnings.filterwarnings("ignore")

# ── Supabase client ──────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
db = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Parameters (unchanged) ───────────────────────────────────────────────────
PARAM_SET = {
    'DOLLAR_VOLUME_MIN': 25_000_000,
    'ADR_MIN': 0.05,
    'PRICE_MIN': 5.0,
    'VOL_CONTRACTION': 1.30,
    'VCP_MAX_RATIO': 0.80,
    'SURGE_MIN': 0.40,
    'SURGE_MAX_DURATION': 30,
    'FLAG_MIN_DURATION': 3,
    'FLAG_MAX_PULLBACK': 0.10,
    'FLAG_MAX_PULLUP': 0.15,
    'SURGE_LOOKBACK': 30,
    'PERF_3M_MIN': 0.00,
    'PERF_6M_MIN': 0.50
}

# ── Fetch tickers ────────────────────────────────────────────────────────────
def get_market_tickers():
    print("Fetching NASDAQ & NYSE tickers...")
    headers = {"User-Agent": "Mozilla/5.0"}
    tickers = []
    for exchange in ["NASDAQ", "NYSE"]:
        url = f"https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5000&exchange={exchange}"
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            df = pd.DataFrame(r.json()["data"]["table"]["rows"])
            sym_col = 'symbol' if 'symbol' in df.columns else df.columns[0]
            df = df[~df[sym_col].str.contains(r'[.\^/WR\-]', regex=True, na=False)]
            tickers.extend([str(row[sym_col]).strip() for _, row in df.iterrows()])
        except Exception as e:
            print(f"  Warning: could not fetch {exchange}: {e}")
    np.random.seed(42)
    np.random.shuffle(tickers)
    print(f"  Found {len(tickers)} tickers")
    return tickers

# ── Download 12 months (enough for all lookbacks, much faster than 10yr) ─────
def download_data(tickers):
    print(f"\nDownloading 12 months of data for {len(tickers)} tickers...")
    all_data = {}
    batch_size = 20                      # down from 40
    total_batches = math.ceil(len(tickers) / batch_size)

    end_date = datetime.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=365)

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        current_batch = (i // batch_size) + 1
        print(f"  Batch {current_batch}/{total_batches}...")

        for attempt in range(3):          # retry up to 3x on rate limit
            try:
                raw = yf.download(
                    batch,
                    start=start_date.strftime('%Y-%m-%d'),
                    end=end_date.strftime('%Y-%m-%d'),
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=False,        # prevents SQLite lock
                )
                break
            except Exception as e:
                msg = str(e)
                if 'Rate' in msg or '429' in msg:
                    wait = (attempt + 1) * 30   # 30s, 60s, 90s
                    print(f"  Rate limited. Waiting {wait}s before retry...")
                    time.sleep(wait)
                else:
                    print(f"  Batch error: {e}")
                    raw = None
                    break
        else:
            print(f"  Skipping batch after 3 failed attempts")
            continue

        if raw is None or raw.empty:
            continue

        for t in batch:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if t in raw.columns.get_level_values(0):
                        df = raw[t].dropna()
                    elif t in raw.columns.get_level_values(1):
                        df = raw.xs(t, axis=1, level=1).dropna()
                    else:
                        continue
                else:
                    df = raw.dropna()

                if not df.empty and len(df) > 130:
                    df['SMA20'] = df['Close'].rolling(20).mean()
                    df['SMA10'] = df['Close'].rolling(10).mean()
                    df['ADR'] = ((df['High'] - df['Low']) / df['Close']).rolling(14).mean()
                    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()
                    df['AvgVol'] = df['Volume'].rolling(20).mean()
                    df['DolVol'] = df['Close'] * df['AvgVol']
                    all_data[t] = df.dropna()
            except:
                pass

        time.sleep(5)                     # up from 2s

    print(f"  Got data for {len(all_data)} stocks")
    return all_data

# ── Scanner (unchanged algorithm) ────────────────────────────────────────────
def scan_stock_history(args):
    ticker, df, p = args
    found_flags = []
    lookback = p['SURGE_LOOKBACK']

    dates_arr  = df.index
    close_arr  = df['Close'].values
    high_arr   = df['High'].values
    low_arr    = df['Low'].values
    vol_arr    = df['Volume'].values
    sma20_arr  = df['SMA20'].values
    adr_arr    = df['ADR'].values
    dolvol_arr = df['DolVol'].values

    last_flag_idx = -999

    for i in range(max(130, lookback), len(close_arr)):
        if i - last_flag_idx < 10:
            continue
        current_close = close_arr[i]
        if current_close < p['PRICE_MIN']: continue
        if current_close < sma20_arr[i]: continue
        if adr_arr[i] < p['ADR_MIN']: continue
        if dolvol_arr[i] < p['DOLLAR_VOLUME_MIN']: continue

        perf_6m = (current_close - close_arr[i - 126]) / close_arr[i - 126]
        if perf_6m < p['PERF_6M_MIN']: continue
        perf_3m = (current_close - close_arr[i - 63]) / close_arr[i - 63]
        if perf_3m < p['PERF_3M_MIN']: continue

        peak_slice = high_arr[i - lookback: i + 1]
        peak = np.max(peak_slice)
        peak_idx = i - lookback + np.argmax(peak_slice)

        low_slice = low_arr[i - lookback: i + 1]
        period_low = np.min(low_slice)
        low_idx = i - lookback + np.argmin(low_slice)

        surge = (peak - period_low) / period_low if period_low > 0 else 0
        if surge < p['SURGE_MIN']: continue

        surge_duration = peak_idx - low_idx
        if surge_duration < 0 or surge_duration > p['SURGE_MAX_DURATION']: continue

        days_since_peak = i - peak_idx
        pullback_depth = (peak - current_close) / peak if peak > 0 else 1.0
        if pullback_depth > p['FLAG_MAX_PULLBACK']: continue
        if days_since_peak < p['FLAG_MIN_DURATION']: continue

        pullup_from_peak = (current_close - peak) / peak if peak > 0 else 0
        if pullup_from_peak > p['FLAG_MAX_PULLUP']: continue

        recent_range = np.mean(high_arr[i - 2: i + 1] - low_arr[i - 2: i + 1])
        surge_range = np.mean(high_arr[i - lookback: i + 1] - low_arr[i - lookback: i + 1])
        if surge_range > 0 and (recent_range / surge_range) > p['VCP_MAX_RATIO']: continue

        flag_vol = np.mean(vol_arr[i - days_since_peak + 1: i + 1])
        surge_vol = np.mean(vol_arr[i - lookback: i - days_since_peak + 1])
        if surge_vol == 0 or (flag_vol / surge_vol) > p['VOL_CONTRACTION']: continue

        found_flags.append((ticker, dates_arr[i]))
        last_flag_idx = i

    return found_flags

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.set_start_method('fork')
    cores = multiprocessing.cpu_count()

    print("=" * 70)
    print(f"  QULLAMAGGIE SCANNER  |  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    tickers = get_market_tickers()
    all_data = download_data(tickers)

    print(f"\nScanning {len(all_data)} stocks across {cores} cores...")

    work_items = [(t, df, PARAM_SET) for t, df in all_data.items()]
    all_flags = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=cores) as executor:
        for result in executor.map(scan_stock_history, work_items):
            if result:
                all_flags.extend(result)

    print(f"Scan complete. {len(all_flags)} total setup instances found.")

    # ── Filter to setups from the last 5 trading days only ──────────────────
    today = datetime.utcnow().date()
    cutoff = today - timedelta(days=7)
    recent_flags = [(t, d) for t, d in all_flags if pd.Timestamp(d).date() >= cutoff]

    print(f"{len(recent_flags)} recent setups (last 7 days)")

    # ── Write to Supabase ────────────────────────────────────────────────────
    scanned_at = datetime.utcnow().isoformat()

    # Delete results older than 60 days to keep the table clean
    old_cutoff = (today - timedelta(days=60)).isoformat()
    db.table('scanner_results').delete().lt('setup_date', old_cutoff).execute()

    if recent_flags:
        rows = [
            {
                'ticker': t,
                'setup_date': pd.Timestamp(d).strftime('%Y-%m-%d'),
                'scanned_at': scanned_at
            }
            for t, d in recent_flags
        ]
        db.table('scanner_results').upsert(rows, on_conflict='ticker,setup_date').execute()
        print(f"Saved {len(rows)} results to Supabase.")
        for t, d in sorted(recent_flags, key=lambda x: x[1], reverse=True):
            print(f"  {pd.Timestamp(d).strftime('%Y-%m-%d')}  {t}")
    else:
        print("No setups from the last 7 days.")
