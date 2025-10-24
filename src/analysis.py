
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, List, Optional

def add_m15_indicators(df):
    """Adds all necessary indicators to the M15 DataFrame."""
    if df is None: return None
    df_copy = df.copy()
    df_copy.columns = [col.lower() for col in df_copy.columns]

    # Add all indicators needed for strategies and feature engineering
    df_copy.ta.rsi(length=14, append=True)
    df_copy.ta.stoch(append=True)
    df_copy.ta.macd(append=True)
    emas = [34, 36, 50, 89, 200]
    for ema in emas:
        df_copy.ta.ema(length=ema, append=True)
    
    # Add all available Candlestick Patterns
    df_copy.ta.cdl_pattern(name="all", append=True)

    df_copy.columns = [col.upper() for col in df_copy.columns]
    return df_copy

def _calculate_trend(df: pd.DataFrame, tf_name: str) -> pd.Series:
    """
    Helper function to calculate the trend for a given timeframe.
    Returns a resampled Series ready to be merged.
    """
    df_copy = df.copy()
    df_copy.columns = [col.lower() for col in df_copy.columns]
    
    # Ensure there's enough data to calculate the EMA
    ema_length = 200
    if len(df_copy) < ema_length:
        print(f"Warning: Not enough data for {tf_name.upper()} to calculate EMA({ema_length}). Skipping trend calculation.")
        return pd.Series(name=f'{tf_name.upper()}_TREND', dtype=float)

    trend_col_name = f'{tf_name.upper()}_TREND'
    df_copy['ema_200'] = ta.ema(df_copy['close'], length=200)
    
    # Sử dụng np.where để xử lý các giá trị NaN một cách an toàn
    # Điều kiện 1: Nếu close > ema_200 -> trend = 1
    # Điều kiện 2: Nếu close < ema_200 -> trend = -1
    # Mặc định: np.nan (cho các hàng không có giá trị ema_200)
    df_copy[trend_col_name] = np.where(df_copy['close'] > df_copy['ema_200'], 1, 
                                     np.where(df_copy['close'] < df_copy['ema_200'], -1, np.nan))

    # Resample to 15min and forward fill
    return df_copy[[trend_col_name]].resample('15min').ffill()

def _calculate_sr(df: pd.DataFrame, tf_name: str, period: int) -> pd.DataFrame:
    """
    Helper function to calculate Support/Resistance for a given timeframe.
    Returns a resampled DataFrame ready to be merged.
    """
    df_copy = df.copy()
    df_copy.columns = [col.lower() for col in df_copy.columns]

    support_col_name = f'{tf_name.upper()}_S'
    resist_col_name = f'{tf_name.upper()}_R'
    
    df_copy[support_col_name] = df_copy['low'].rolling(window=period).min()
    df_copy[resist_col_name] = df_copy['high'].rolling(window=period).max()
    
    if tf_name.upper() == 'M15':
        return df_copy[[support_col_name, resist_col_name]]
    else:
        return df_copy[[support_col_name, resist_col_name]].resample('15min').ffill()

def find_supply_demand_zones(df: pd.DataFrame, lookback: int = 100, impulse_threshold: float = 1.5):
    """
    Xác định các Vùng Cung và Cầu tiềm năng dựa trên các cú bứt phá giá.

    Args:
        df (pd.DataFrame): Dữ liệu OHLC đầu vào.
        lookback (int): Số lượng nến để quét tìm các vùng.
        impulse_threshold (float): Hệ số nhân so với thân nến trung bình để xác định một cú bứt phá.

    Returns:
        tuple: Một tuple chứa hai danh sách: (supply_zones, demand_zones).
               Mỗi vùng là một dictionary với 'high' và 'low'.
    """
    zones_df = df.tail(lookback).copy()
    zones_df['body_size'] = abs(zones_df['CLOSE'] - zones_df['OPEN'])
    avg_body_size = zones_df['body_size'].mean()
    impulse_move = avg_body_size * impulse_threshold

    supply_zones = []
    demand_zones = []

    for i in range(1, len(zones_df)):
        # Nến bứt phá giảm (Impulse Down) -> Tạo Vùng Cung (Supply)
        if (zones_df['OPEN'].iloc[i] - zones_df['CLOSE'].iloc[i]) > impulse_move:
            base_candle = zones_df.iloc[i-1]
            # Vùng cung được xác định bởi giá cao nhất và thấp nhất của nến "cơ sở" trước đó.
            supply_zones.append({'high': base_candle['HIGH'], 'low': base_candle['LOW']})

        # Nến bứt phá tăng (Impulse Up) -> Tạo Vùng Cầu (Demand)
        elif (zones_df['CLOSE'].iloc[i] - zones_df['OPEN'].iloc[i]) > impulse_move:
            base_candle = zones_df.iloc[i-1]
            # Vùng cầu được xác định bởi giá cao nhất và thấp nhất của nến "cơ sở" trước đó.
            demand_zones.append({'high': base_candle['HIGH'], 'low': base_candle['LOW']})

    return supply_zones, demand_zones

def add_nearest_sd_zones(base_df: pd.DataFrame, timeframes_data: Dict[str, pd.DataFrame]):
    """
    Tính toán và thêm các cột chứa mức giá của vùng Cung/Cầu gần nhất.
    được xác định từ các khung thời gian cao (H4, D1).
    """
    df_copy = base_df.copy()
    all_supply_zones = []
    all_demand_zones = []

    # Quét các khung thời gian cao để tìm vùng Cung/Cầu
    for tf_name in ['h4', 'd1']:
        if tf_name in timeframes_data:
            print(f"Finding Supply/Demand zones on {tf_name.upper()}...")
            supply, demand = find_supply_demand_zones(timeframes_data[tf_name])
            all_supply_zones.extend(supply)
            all_demand_zones.extend(demand)
    
    current_price = df_copy['CLOSE'].iloc[-1]

    # Tìm vùng Cung gần nhất phía trên giá hiện tại
    nearest_supply = min([zone['low'] for zone in all_supply_zones if zone['low'] > current_price], default=np.nan)
    
    # Tìm vùng Cầu gần nhất phía dưới giá hiện tại
    nearest_demand = max([zone['high'] for zone in all_demand_zones if zone['high'] < current_price], default=np.nan)

    # Thêm vào hàng cuối cùng của DataFrame
    df_copy.loc[df_copy.index[-1], 'NEAREST_SUPPLY'] = nearest_supply
    df_copy.loc[df_copy.index[-1], 'NEAREST_DEMAND'] = nearest_demand
    
    return df_copy

def prepare_analysis_data(timeframes_data, sr_periods, include_sd_zones=False):
    """ 
    The main data preparation function.
    Prepares M15 data by adding all indicators and merging S/R and Trend info from higher timeframes.
    """
    required_tfs = ['m15', 'h4'] # D1 is optional for EMA strategy
    if not all(tf in timeframes_data for tf in required_tfs):
        print(f"Error: Not all required timeframes data were provided. Missing one of {required_tfs}")
        return None

    # 1. Add all base indicators to M15 chart
    print("Adding indicators to M15 data...")
    m15_df = add_m15_indicators(timeframes_data['m15'])
    if m15_df is None:
        return None

    # 2. Calculate all higher timeframe features and collect them
    higher_tf_features: List[pd.DataFrame] = []

    # Calculate Trends
    # Thêm H1 vào danh sách các khung thời gian cần tính xu hướng
    trend_timeframes = {'h4': timeframes_data['h4']} # Bắt buộc
    if 'd1' in timeframes_data:
        trend_timeframes['d1'] = timeframes_data['d1']
    if 'm30' in timeframes_data:
        trend_timeframes['m30'] = timeframes_data['m30']
    if 'h1' in timeframes_data:
        trend_timeframes['h1'] = timeframes_data['h1']

    for tf_name, df in trend_timeframes.items():
        print(f"Calculating {tf_name.upper()} Trend...")
        higher_tf_features.append(_calculate_trend(df, tf_name))

    # Calculate S/R
    for tf_name, df in timeframes_data.items():
        period = sr_periods.get(tf_name, 200)
        print(f"Calculating S/R for {tf_name.upper()} with period {period}...")
        sr_df = _calculate_sr(df, tf_name, period)
        if tf_name.upper() == 'M15':
            # For M15, merge directly since it's the base dataframe
            m15_df = pd.concat([m15_df, sr_df], axis=1)
        else:
            higher_tf_features.append(sr_df)

    # 3. Merge all higher timeframe features in one go
    if higher_tf_features:
        print("Merging all higher timeframe features...")
        m15_df = pd.concat([m15_df] + higher_tf_features, axis=1)
    
    # 5. Find and add nearest Supply/Demand zones
    if include_sd_zones:
        # Truyền tất cả dữ liệu khung thời gian để hàm có thể quét trên H4 và D1
        m15_df = add_nearest_sd_zones(m15_df, timeframes_data)

    # 4. Final cleanup
    m15_df.ffill(inplace=True)
    m15_df.dropna(inplace=True)

    print("Comprehensive data preparation complete.")
    return m15_df

def prepare_scalping_data(timeframes_data: Dict[str, pd.DataFrame], strategy_params: Dict) -> Optional[pd.DataFrame]:
    """
    Chuẩn bị dữ liệu cho chiến lược scalping.
    - Base timeframe: M1
    - Execution timeframe: M5
    - Trend timeframe: M15
    """
    required_tfs = ['m1', 'm5', 'm15']
    if not all(tf in timeframes_data for tf in required_tfs):
        print("Lỗi: Không cung cấp đủ dữ liệu cho các khung thời gian M1, M5, M15.")
        return None

    m1_df = timeframes_data['m1'].copy()
    m5_df = timeframes_data['m5'].copy()
    m15_df = timeframes_data['m15'].copy()

    # --- 1. Tính toán xu hướng trên M15 ---
    print("Đang tính xu hướng trên M15...")
    m15_df.columns = [col.lower() for col in m15_df.columns]
    m15_ema_200 = ta.ema(m15_df['close'], length=200)
    # Add M15 EMA 34 and 89 for the new strategy
    m15_df['M15_EMA_34'] = ta.ema(m15_df['close'], length=34)
    m15_df['M15_EMA_89'] = ta.ema(m15_df['close'], length=89)

    # Sửa lỗi logic: So sánh giá đóng cửa của mỗi nến với giá trị EMA tương ứng
    # thay vì so sánh với giá đóng cửa cuối cùng.
    m15_df['M15_TREND_EMA200'] = np.where(m15_df['close'] > m15_ema_200, 1, -1)
    # Xử lý các giá trị NaN ở đầu
    m15_df['M15_TREND_EMA200'] = m15_df['M15_TREND_EMA200'].fillna(0)
    # Resample all necessary M15 indicators
    m15_indicators_resampled = m15_df[['M15_TREND_EMA200', 'M15_EMA_34', 'M15_EMA_89']].resample('1min').ffill()
    
    # --- Thêm chỉ báo xu hướng từ H1 và M30 ---
    all_htf_features = [m15_indicators_resampled]
    
    if 'h1' in timeframes_data:
        print("Đang tính xu hướng trên H1...")
        h1_df = timeframes_data['h1'].copy()
        h1_df.columns = [col.lower() for col in h1_df.columns]
        h1_df['H1_TREND'] = np.where(h1_df['close'] > ta.ema(h1_df['close'], length=200), 1, -1)
        all_htf_features.append(h1_df[['H1_TREND']].resample('1min').ffill())

    if 'm30' in timeframes_data:
        print("Đang tính xu hướng trên M30...")
        m30_df = timeframes_data['m30'].copy()
        m30_df.columns = [col.lower() for col in m30_df.columns]
        m30_df['M30_TREND'] = np.where(m30_df['close'] > ta.ema(m30_df['close'], length=200), 1, -1)
        all_htf_features.append(m30_df[['M30_TREND']].resample('1min').ffill())

    # --- 2. Tính toán các chỉ báo trên M5 ---
    print("Đang tính các chỉ báo EMA trên M5...")
    m5_df.columns = [col.lower() for col in m5_df.columns]
    
    # Lấy tham số EMA từ config, nếu không có thì dùng mặc định
    ema_fast_len = strategy_params.get('ema_fast_len', 9) if strategy_params else 9
    ema_slow_len = strategy_params.get('ema_slow_len', 20) if strategy_params else 20
    
    # Tính toán cả EMA và RSI
    m5_df.ta.ema(length=ema_fast_len, append=True, col_names=(f'M5_EMA_{ema_fast_len}',))
    m5_df.ta.ema(length=ema_slow_len, append=True, col_names=(f'M5_EMA_{ema_slow_len}',))
    m5_df.ta.rsi(length=14, append=True, col_names=('RSI_14',))
    
    m5_indicators = m5_df[[f'M5_EMA_{ema_fast_len}', f'M5_EMA_{ema_slow_len}', 'RSI_14']].resample('1min').ffill()

    # --- 3. Hợp nhất tất cả dữ liệu vào khung M1 ---
    print("Đang hợp nhất dữ liệu...")
    # Đảm bảo các cột của m1_df là chữ hoa để nhất quán
    m1_df.columns = [col.upper() for col in m1_df.columns]
    
    merged_df = pd.concat([m1_df] + all_htf_features + [m5_indicators], axis=1)

    # --- 4. Dọn dẹp dữ liệu ---
    merged_df.ffill(inplace=True)
    merged_df.dropna(inplace=True)

    print("Chuẩn bị dữ liệu scalping hoàn tất.")
    return merged_df
