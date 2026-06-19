"""
QULLAMAGGIE 5-STAR SETUP SCANNER
Runs via GitHub Actions, writes results to Supabase.
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

import shutil
import random
import yfinance as yf

if os.path.exists("/tmp/yf_cache"):
    shutil.rmtree("/tmp/yf_cache")
os.makedirs("/tmp/yf_cache", exist_ok=True)
yf.set_tz_cache_location("/tmp/yf_cache")

import pandas as pd
import numpy as np
import requests
import warnings
import time
import multiprocessing
import concurrent.futures
from datetime import datetime, timedelta
from supabase import create_client

warnings.filterwarnings("ignore")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
db = create_client(SUPABASE_URL, SUPABASE_KEY)

AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
]

def update_progress(status, done=0, total=0):
    for attempt in range(3):
        try:
            db.table('scanner_progress').update({
                'status': status,
                'tickers_done': done,
                'tickers_total': total,
                'updated_at': datetime.utcnow().isoformat(),
            }).eq('id', 1).execute()
            print(f"  [progress] {status} {done}/{total}", flush=True)
            return
        except Exception as e:
            print(f"  Progress update failed (attempt {attempt+1}): {e}", flush=True)
            time.sleep(2)

PARAM_SET = {
    'DOLLAR_VOLUME_MIN': 25_000_000,
    'ADR_MIN': 0.05,
    'PRICE_MIN': 5.0,
    'VOL_CONTRACTION': 1.40,
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

def get_market_tickers():
    print("Fetching NASDAQ & NYSE tickers...")
    headers = {"User-Agent": random.choice(AGENTS)}
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

def fetch_one(t, session):
    df = yf.Ticker(t, session=session).history(
        period='1y',
        interval='1d',
        auto_adjust=True,
        raise_errors=True,
    )
    return df

def download_data(tickers):
    print(f"\nDownloading data for {len(tickers)} tickers over ~2 hours...", flush=True)
    all_data = {}
    timed_out = 0
    rate_limited = 0
    failed = 0

    # Spread evenly over 2 hours (7200 seconds) with ±30% jitter
    base_delay = 7200 / len(tickers)
    jitter = base_delay * 0.3
    print(f"  Base delay per ticker: {base_delay:.2f}s (±{jitter:.2f}s jitter) — ~2hr total", flush=True)

    session = requests.Session()
    session.headers.update({
        'User-Agent': random.choice(AGENTS),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    })

    for i, t in enumerate(tickers):
        if i % 50 == 0 and i > 0:
            session.headers.update({'User-Agent': random.choice(AGENTS)})

        if i % 25 == 0:
            remaining_min = ((len(tickers) - i) * base_delay) / 60
            print(f"  {i}/{len(tickers)} — {len(all_data)} loaded | "
                  f"timeouts={timed_out} rate_limits={rate_limited} failed={failed} | "
                  f"~{remaining_min:.0f}min remaining", flush=True)
            update_progress('downloading', i, len(tickers))

        for attempt in range(2):
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as tex:
                    future = tex.submit(fetch_one, t, session)
                    try:
                        df = future.result(timeout=30)
                    except concurrent.futures.TimeoutError:
                        timed_out += 1
                        print(f"  Timeout: {t} — skipping", flush=True)
                        break

                if df is None or df.empty or len(df) < 130:
                    break

                df['SMA20']  = df['Close'].rolling(20).mean()
                df['SMA10']  = df['Close'].rolling(10).mean()
                df['ADR']    = ((df['High'] - df['Low']) / df['Close']).rolling(14).mean()
                df['ATR']    = (df['High'] - df['Low']).rolling(14).mean()
                df['AvgVol'] = df['Volume'].rolling(20).mean()
                df['DolVol'] = df['Close'] * df['AvgVol']
                df = df.dropna()

                if not df.empty:
                    all_data[t] = df
                break

            except Exception as e:
                msg = str(e)
                if 'Rate' in msg or '429' in msg or 'Too Many' in msg:
                    rate_limited += 1
                    print(f"  Rate limited: {t} — skipping", flush=True)
                    time.sleep(2)
                    break
                else:
                    failed += 1
                    break

        # Spread requests evenly over 2 hours with random jitter
        sleep_time = base_delay + random.uniform(-jitter, jitter)
        time.sleep(max(sleep_time, 1.0))

    print(f"\n  Done. Loaded={len(all_data)} | Timeouts={timed_out} | "
          f"RateLimited={rate_limited} | Failed={failed}", flush=True)
    return all_data

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

        # VCP ratio measured as % daily range relative to closing price, not raw
        # dollar range — keeps the comparison valid across the price change that
        # happens between the start of the surge window and the flag.
        recent_pct_range = np.mean(
            (high_arr[i - 2: i + 1] - low_arr[i - 2: i + 1]) / close_arr[i - 2: i + 1]
        )
        surge_pct_range = np.mean(
            (high_arr[i - lookback: i + 1] - low_arr[i - lookback: i + 1]) / close_arr[i - lookback: i + 1]
        )
        if surge_pct_range > 0 and (recent_pct_range / surge_pct_range) > p['VCP_MAX_RATIO']: continue

        flag_vol = np.mean(vol_arr[i - days_since_peak + 1: i + 1])
        surge_vol = np.mean(vol_arr[i - lookback: i - days_since_peak + 1])
        if surge_vol == 0 or (flag_vol / surge_vol) > p['VOL_CONTRACTION']: continue

        found_flags.append((ticker, dates_arr[i]))
        last_flag_idx = i

    return found_flags

if __name__ == "__main__":
    multiprocessing.set_start_method('fork')
    cores = multiprocessing.cpu_count()

    print("=" * 70)
    print(f"  QULLAMAGGIE SCANNER  |  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    update_progress('running', 0, 0)

    tickers = get_market_tickers()
    update_progress('downloading', 0, len(tickers))

    all_data = download_data(tickers)
    update_progress('scanning', 0, len(all_data))

    print(f"\nScanning {len(all_data)} stocks across {cores} cores...", flush=True)

    work_items = [(t, df, PARAM_SET) for t, df in all_data.items()]
    all_flags = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=cores) as executor:
        for result in executor.map(scan_stock_history, work_items):
            if result:
                all_flags.extend(result)

    print(f"Scan complete. {len(all_flags)} total setup instances found.", flush=True)

    update_progress('saving', len(all_flags), len(all_data))

    today = datetime.utcnow().date()
    cutoff = today - timedelta(days=7)
    recent_flags = [(t, d) for t, d in all_flags if pd.Timestamp(d).date() >= cutoff]

    print(f"{len(recent_flags)} recent setups (last 7 days)", flush=True)

    scanned_at = datetime.utcnow().isoformat()
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
        print(f"Saved {len(rows)} results to Supabase.", flush=True)
        for t, d in sorted(recent_flags, key=lambda x: x[1], reverse=True):
            print(f"  {pd.Timestamp(d).strftime('%Y-%m-%d')}  {t}")
    else:
        print("No setups from the last 7 days.")

    update_progress('idle', len(all_flags), len(all_data))
    print("\nDone.", flush=True)
