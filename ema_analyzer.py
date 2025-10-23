import pandas as pd
import pandas_ta as ta
from scipy.signal import find_peaks
import numpy as np
import io
import os

def parse_data(filepath):
    try:
        if not os.path.exists(filepath):
            print(f"Error: File not found at path: {filepath}")
            return None
            
        df = pd.read_csv(filepath, sep='\t', engine='python')
        
        df.columns = [col.replace('<', '').replace('>', '') for col in df.columns]
        
        df['DATETIME'] = pd.to_datetime(df['DATE'] + ' ' + df['TIME'])
        df = df.set_index('DATETIME')
        
        df = df[['OPEN', 'HIGH', 'LOW', 'CLOSE']]
        
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Error processing file {filepath}: {e}")
        return None

timeframes = ["M15", "M30", "H1", "H4"]
file_paths = {
    "M15": "Data/XAUUSD_M15_202101040100_202510201415.csv",
    "M30": "Data/XAUUSD_M30_202101040100_202510201400.csv",
    "H1": "Data/XAUUSD_H1_202101040100_202510201400.csv",
    "H4": "Data/XAUUSD_H4_202101040000_202510201200.csv"
}

dataframes = {tf: parse_data(path) for tf, path in file_paths.items()}

results = {}

PEAK_DISTANCE = 15
# Updated EMA_RANGE as per user request
EMA_RANGE = range(200, 301)
TOUCH_THRESHOLD = 0.0005

for timeframe, df in dataframes.items():
    if df is None or df.empty:
        print(f"Skipping {timeframe} due to data loading error or empty dataframe.")
        continue

    high_peaks_indices, _ = find_peaks(df['HIGH'], distance=PEAK_DISTANCE)
    low_peaks_indices, _ = find_peaks(-df['LOW'], distance=PEAK_DISTANCE)

    best_ema = -1
    max_touches = -1

    print(f"Analyzing timeframe {timeframe}...")

    for ema_period in EMA_RANGE:
        ema_series = ta.ema(df['CLOSE'], length=ema_period)
        if ema_series is None:
            continue

        current_touches = 0

        for i in high_peaks_indices:
            if i < ema_period: continue
            peak_high = df['HIGH'].iloc[i]
            ema_value = ema_series.iloc[i]
            if not np.isnan(ema_value) and abs(ema_value - peak_high) <= peak_high * TOUCH_THRESHOLD:
                current_touches += 1

        for i in low_peaks_indices:
            if i < ema_period: continue
            peak_low = df['LOW'].iloc[i]
            ema_value = ema_series.iloc[i]
            if not np.isnan(ema_value) and abs(ema_value - peak_low) <= peak_low * TOUCH_THRESHOLD:
                current_touches += 1

        if current_touches > max_touches:
            max_touches = current_touches
            best_ema = ema_period
            
    results[timeframe] = {'best_ema': best_ema, 'touches': max_touches}

print("\n" + "="*40)
print("Optimal EMA analysis complete for range 200-300.")
print("Best EMA results for each timeframe:")
for timeframe, result in results.items():
    if result.get('best_ema', -1) != -1:
        print(f"  - {timeframe}: EMA {result['best_ema']} (touches: {result['touches']})")
    else:
        print(f"  - {timeframe}: No suitable EMA found.")
print("="*40)
print("Note: These EMA values are the best candidates based on the criterion of touching local peaks/troughs. They should be verified during the backtesting phase.")