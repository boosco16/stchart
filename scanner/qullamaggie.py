"""
QULLAMAGGIE 5-STAR SETUP SCANNER (NUMPY HYPER-SPEED)
=============================================================================
Maps the pure "Coiled Spring" with a rigid Peak Channel and Explosive Surge duration.

SETUP (one-time):
    pip install supabase
    export SUPABASE_URL="https://your-project.supabase.co"
    export SUPABASE_SERVICE_KEY="your-service-key"

    Or add both lines to ~/.zshrc so they persist across terminal sessions.
"""

import os
# ── DISABLE APPLE BACKGROUND THREADING TO PREVENT DEADLOCKS ──
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ['YF_NO_CACHE'] = '1'

import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import warnings
import time
import math
import multiprocessing
import concurrent.futures
import pickle
from datetime import datetime, timedelta
from supabase import create_client

warnings.filterwarnings("ignore")

# ── Supabase connection ───────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_KEY must be set as environment variables.")
    print("  export SUPABASE_URL='https://your-project.supabase.co'")
    print("  export SUPABASE_SERVICE_KEY='your-service-key'")
    exit(1)

db = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── 1. The Target Flag Architecture ──────────────────────────────────────────
PARAM_SET = {
    'DOLLAR_VOLUME_MIN': 25_000_000,   
    'ADR_MIN': 0.05,                         
    'PRICE_MIN': 5.0,              
    'VOL_CONTRACTION': 1.40,           
    'VCP_MAX_RATIO': 0.80,             
    'SURGE_MIN': 0.40,
    'SURGE_MAX_DURATION': 50,           # <--- NEW: Surge must explode in 5 days or less
    'FLAG_MIN_DURATION': 3,
    'FLAG_MAX_PULLBACK': 0.10,
    'FLAG_MAX_PULLUP': 0.15,           
    'SURGE_LOOKBACK': 30,
    'PERF_3M_MIN': 0.00,
    'PERF_6M_MIN': 0.50
}

# ── Progress reporter ─────────────────────────────────────────────────────────
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

# ── 2. Data Fetching & Save State ────────────────────────────────────────────
def get_market_tickers():
    print("Pinging NASDAQ & NYSE...")
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
        except: pass
    
    np.random.seed(42)
    np.random.shuffle(tickers)
    return tickers 

def download_data(tickers):
    save_file = "market_data_10yr.pkl"
    
    if os.path.exists(save_file):
        print(f"\n[+] Found existing data file '{save_file}'!")
        print("Loading 10 years of market data from your hard drive... (Takes ~5 seconds)")
        with open(save_file, "rb") as f:
            return pickle.load(f)
            
    print(f"\nDownloading 10 Years of Daily Data for {len(tickers)} stocks...")
    update_progress('downloading', 0, len(tickers))
    all_data = {}
    batch_size = 40 
    total_batches = math.ceil(len(tickers) / batch_size)

    # Captures today's delayed/live data
    end_date = datetime.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=3650) 

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        current_batch = (i // batch_size) + 1
        print(f"  -> Fetching batch {current_batch} of {total_batches}...")
        update_progress('downloading', i, len(tickers))
        
        try:
            raw = yf.download(
                batch, 
                start=start_date.strftime('%Y-%m-%d'), 
                end=end_date.strftime('%Y-%m-%d'), 
                interval="1d", 
                auto_adjust=True, 
                progress=False, 
                threads=5
            )
        except Exception as e: continue
        
        for t in batch:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    if t in raw.columns.get_level_values(0): df = raw[t].dropna()
                    elif t in raw.columns.get_level_values(1): df = raw.xs(t, axis=1, level=1).dropna()
                    else: continue
                else: df = raw.dropna()
                
                if not df.empty and len(df) > 130: 
                    df['SMA20'] = df['Close'].rolling(20).mean()
                    df['SMA10'] = df['Close'].rolling(10).mean()
                    df['ADR'] = ((df['High'] - df['Low']) / df['Close']).rolling(14).mean()
                    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean() 
                    df['AvgVol'] = df['Volume'].rolling(20).mean()
                    df['DolVol'] = df['Close'] * df['AvgVol']
                    all_data[t] = df.dropna()
            except: pass
        time.sleep(3)

    with open(save_file, "wb") as f:
        pickle.dump(all_data, f)
        
    return all_data

# ── 3. Historical Scanner Engine (NumPy Optimized) ───────────────────────────
def scan_stock_history(args):
    """Scans a single stock's entire history for perfectly coiled setup days"""
    ticker, df, p = args
    found_flags = []
    lookback = p['SURGE_LOOKBACK']
    
    dates_arr = df.index
    close_arr = df['Close'].values
    high_arr  = df['High'].values
    low_arr   = df['Low'].values
    vol_arr   = df['Volume'].values
    sma20_arr = df['SMA20'].values
    adr_arr   = df['ADR'].values
    dolvol_arr= df['DolVol'].values
    
    last_flag_idx = -999  # Cooldown tracker
    
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

        peak_slice = high_arr[i - lookback : i + 1]
        peak = np.max(peak_slice)
        peak_idx = i - lookback + np.argmax(peak_slice)
        
        low_slice = low_arr[i - lookback : i + 1]
        period_low = np.min(low_slice)
        low_idx = i - lookback + np.argmin(low_slice)

        surge = (peak - period_low) / period_low if period_low > 0 else 0
        if surge < p['SURGE_MIN']: continue
        
        # ── THE NEW EXPLOSIVE SURGE FILTER ──
        # Ensure the run up from the low to the peak took 5 days or less
        surge_duration = peak_idx - low_idx
        # Need to ensure low_idx is actually before peak_idx
        if surge_duration < 0 or surge_duration > p['SURGE_MAX_DURATION']: continue

        days_since_peak = i - peak_idx
        
        # 1. Ensure it didn't pull back too far below the peak
        pullback_depth = (peak - current_close) / peak if peak > 0 else 1.0
        if pullback_depth > p['FLAG_MAX_PULLBACK']: continue 
        
        # 2. Minimum consolidation time
        if days_since_peak < p['FLAG_MIN_DURATION']: continue

        # 3. Peak Pullup Logic
        pullup_from_peak = (current_close - peak) / peak if peak > 0 else 0
        if pullup_from_peak > p['FLAG_MAX_PULLUP']: continue

        # VCP ratio measured as % daily range relative to closing price, not raw
        # dollar range — keeps the comparison valid across the price change that
        # happens between the start of the surge window and the flag.
        recent_pct_range = np.mean(
            (high_arr[i - 2 : i + 1] - low_arr[i - 2 : i + 1]) / close_arr[i - 2 : i + 1]
        )
        surge_pct_range = np.mean(
            (high_arr[i - lookback : i + 1] - low_arr[i - lookback : i + 1]) / close_arr[i - lookback : i + 1]
        )
        if surge_pct_range > 0 and (recent_pct_range / surge_pct_range) > p['VCP_MAX_RATIO']: continue

        flag_vol = np.mean(vol_arr[i - days_since_peak + 1 : i + 1])
        surge_vol = np.mean(vol_arr[i - lookback : i - days_since_peak + 1])
        if surge_vol == 0 or (flag_vol / surge_vol) > p['VOL_CONTRACTION']: continue
            
        found_flags.append((ticker, dates_arr[i]))
        last_flag_idx = i  

    return found_flags

# ── MAIN EXECUTION ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    multiprocessing.set_start_method('fork')
    cores = multiprocessing.cpu_count()
    
    print("=" * 90)
    print(f"  QULLAMAGGIE 5-STAR SETUP SCANNER (NUMPY ENGINE - {cores} CORES)")
    print("=" * 90)

    update_progress('running', 0, 0)

    tickers = get_market_tickers()
    all_data = download_data(tickers)

    print(f"\nCommencing full-market historical scan across {cores} threads... Stand by.")
    update_progress('scanning', 0, len(all_data))

    work_items = [(t, df, PARAM_SET) for t, df in all_data.items()]
    all_flags = []

    with concurrent.futures.ProcessPoolExecutor(max_workers=cores) as executor:
        for result in executor.map(scan_stock_history, work_items):
            if result:
                all_flags.extend(result)

    print("\nScan complete!")

    if len(all_flags) == 0:
        print("\nZERO setups found in the last 10 years.")
        update_progress('idle', 0, len(all_data))
    else:
        # Convert raw tuples into a Pandas DataFrame
        df_flags = pd.DataFrame(all_flags, columns=['Ticker', 'Date'])
        df_flags['Date'] = pd.to_datetime(df_flags['Date'])
        df_flags['Year'] = df_flags['Date'].dt.year
        df_flags['Month'] = df_flags['Date'].dt.month
        
        # Build the Pivot Table
        heatmap = df_flags.pivot_table(
            index='Year', 
            columns='Month', 
            values='Ticker', 
            aggfunc='count', 
            fill_value=0
        )
        
        heatmap['TOTAL'] = heatmap.sum(axis=1)
        
        month_names = {1:'Jan', 2:'Feb', 3:'Mar', 4:'Apr', 5:'May', 6:'Jun', 
                       7:'Jul', 8:'Aug', 9:'Sep', 10:'Oct', 11:'Nov', 12:'Dec'}
        heatmap.rename(columns=month_names, inplace=True)

        print("\n" + "=" * 80)
        print("  📅 HISTORICAL 5-STAR SETUPS (Perfectly Coiled Flags Per Month)")
        print("=" * 80)
        print(heatmap.to_string())
        print("=" * 80)

        print("\n" + "=" * 80)
        print("  🎯 SPECIFIC 5-STAR SETUPS IN 2026")
        print("=" * 80)
        
        df_2026 = df_flags[df_flags['Year'] == 2026].sort_values(by='Date')
        
        if df_2026.empty:
            print("  No setups have fully formed yet in 2026.")
        else:
            for index, row in df_2026.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                print(f"  [>] {date_str} | {row['Ticker']}")
        print("=" * 80)

        # ── Write to Supabase ─────────────────────────────────────────────────
        print("\nSaving results to Supabase...", flush=True)
        update_progress('saving', len(all_flags), len(all_data))

        today = datetime.utcnow().date()
        cutoff = today - timedelta(days=7)
        recent_flags = [(t, d) for t, d in all_flags if pd.Timestamp(d).date() >= cutoff]

        print(f"{len(recent_flags)} recent setups (last 7 days)", flush=True)

        scanned_at = datetime.utcnow().isoformat()
        old_cutoff = (today - timedelta(days=60)).isoformat()
        db.table('scanner_results').delete().lt('setup_date', old_cutoff).execute()

        if recent_flags:
            # Fetch sector for each flagged ticker (small list, fast)
            print("Fetching sector data for flagged tickers...", flush=True)
            unique_tickers = list({t for t, _ in recent_flags})
            sector_map = {}
            for t in unique_tickers:
                try:
                    info = yf.Ticker(t).info
                    sector_map[t] = info.get('sector', 'Unknown') or 'Unknown'
                except Exception:
                    sector_map[t] = 'Unknown'

            rows = [
                {
                    'ticker': t,
                    'setup_date': pd.Timestamp(d).strftime('%Y-%m-%d'),
                    'scanned_at': scanned_at,
                    'sector': sector_map.get(t, 'Unknown')
                }
                for t, d in recent_flags
            ]
            db.table('scanner_results').upsert(rows, on_conflict='ticker,setup_date').execute()
            print(f"Saved {len(rows)} results to Supabase.", flush=True)
        else:
            print("No setups from the last 7 days — nothing written.", flush=True)

        update_progress('idle', len(all_flags), len(all_data))

    print("\nDone.", flush=True)
