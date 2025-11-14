# -*- coding: utf-8 -*-
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
    df_copy.ta.adx(append=True)
    df_copy.ta.atr(append=True) # This creates 'ATRr_14'

    # Add SMA of ATR for volatility filter
    # Ensure the ATR column exists before trying to calculate its SMA
    if 'ATRr_14' in df_copy.columns:
        df_copy['ATRr_14_SMA_50'] = ta.sma(df_copy['ATRr_14'], length=50)

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


def _calculate_cpr(d1_data: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates the Central Pivot Range (CPR) levels for the next day.
    """
    if d1_data is None or d1_data.empty:
        return pd.DataFrame()

    # Make sure the columns are uppercase
    d1_data.columns = [col.upper() for col in d1_data.columns]

    cpr_df = pd.DataFrame(index=d1_data.index)
    cpr_df['prev_high'] = d1_data['HIGH'].shift(1)
    cpr_df['prev_low'] = d1_data['LOW'].shift(1)
    cpr_df['prev_close'] = d1_data['CLOSE'].shift(1)

    cpr_df['pivot'] = (cpr_df['prev_high'] + cpr_df['prev_low'] + cpr_df['prev_close']) / 3
    cpr_df['bc'] = (cpr_df['prev_high'] + cpr_df['prev_low']) / 2
    cpr_df['tc'] = (cpr_df['pivot'] - cpr_df['bc']) + cpr_df['pivot']
    
    # Rename columns for clarity
    cpr_df.rename(columns={'pivot': 'CPR_PIVOT', 'bc': 'CPR_BC', 'tc': 'CPR_TC'}, inplace=True)

    return cpr_df[['CPR_PIVOT', 'CPR_BC', 'CPR_TC']]


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

def _calculate_indicators_for_tf(df: pd.DataFrame, tf_name: str, strategy_params: Dict) -> pd.DataFrame:
    """
    Hàm trợ giúp để tính toán tất cả các chỉ báo cần thiết cho một khung thời gian cụ thể.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df_copy = df.copy()
    df_copy.columns = [col.upper() for col in df_copy.columns]

    # Lấy tham số từ config
    ema_params = strategy_params.get('ScalpingEmaCrossoverStrategy', {})
    ema_fast_len = ema_params.get('ema_fast_len', 9)
    ema_slow_len = ema_params.get('ema_slow_len', 20)

    bb_params = strategy_params.get('BollingerBandMeanReversionStrategy', {})
    bb_length = bb_params.get('bb_length', 20)
    bb_std_dev = bb_params.get('bb_std_dev', 2.0)

    m15_filter_params = strategy_params.get('M15FilteredScalpingStrategy', {})
    adx_length = m15_filter_params.get('adx_length', 14)

    # Tính toán chỉ báo dựa trên khung thời gian
    if tf_name == 'm5':
        df_copy[f'M5_EMA_{ema_fast_len}'] = ta.ema(df_copy['CLOSE'], length=ema_fast_len)
        df_copy[f'M5_EMA_{ema_slow_len}'] = ta.ema(df_copy['CLOSE'], length=ema_slow_len)
        df_copy['RSI_14'] = ta.rsi(df_copy['CLOSE'], length=14)
        df_copy['ATR_14_M5'] = ta.atr(high=df_copy['HIGH'], low=df_copy['LOW'], close=df_copy['CLOSE'], length=14)
        bbands_indicator = ta.bbands(close=df_copy['CLOSE'], length=bb_length, std=bb_std_dev)
        if bbands_indicator is not None and not bbands_indicator.empty:
            df_copy = df_copy.join(bbands_indicator)

    elif tf_name == 'm15':
        df_copy['M15_EMA_34'] = ta.ema(df_copy['CLOSE'], length=34)
        df_copy['M15_EMA_89'] = ta.ema(df_copy['CLOSE'], length=89)
        m15_ema_200 = ta.ema(df_copy['CLOSE'], length=200)
        df_copy['M15_TREND_EMA200'] = np.where(df_copy['CLOSE'] > m15_ema_200, 1, -1)
        df_copy['ATR_14_M15'] = ta.atr(high=df_copy['HIGH'], low=df_copy['LOW'], close=df_copy['CLOSE'], length=14)
        df_copy['RSI_14_M15'] = ta.rsi(df_copy['CLOSE'], length=14)
        adx_indicator = ta.adx(high=df_copy['HIGH'], low=df_copy['LOW'], close=df_copy['CLOSE'], length=adx_length)
        if adx_indicator is not None and f'ADX_{adx_length}' in adx_indicator.columns:
            df_copy[f'ADX_{adx_length}_M15'] = adx_indicator[f'ADX_{adx_length}']

    elif tf_name == 'm30':
        m30_ema_200 = ta.ema(df_copy['CLOSE'], length=200)
        df_copy['M30_TREND'] = np.where(df_copy['CLOSE'] > m30_ema_200, 1, -1)

    elif tf_name == 'h1':
        df_copy['H1_EMA_34'] = ta.ema(df_copy['CLOSE'], length=34)
        df_copy['H1_EMA_89'] = ta.ema(df_copy['CLOSE'], length=89)
        h1_ema_200 = ta.ema(df_copy['CLOSE'], length=200)
        df_copy['H1_TREND'] = np.where(df_copy['CLOSE'] > h1_ema_200, 1, -1)

    elif tf_name == 'h4':
        df_copy['H4_EMA_34'] = ta.ema(df_copy['CLOSE'], length=34)
        df_copy['H4_EMA_89'] = ta.ema(df_copy['CLOSE'], length=89)
        h4_ema_200 = ta.ema(df_copy['CLOSE'], length=200)
        df_copy['H4_TREND'] = np.where(df_copy['CLOSE'] > h4_ema_200, 1, -1)

    # Đổi tên các cột OHLC gốc để tránh trùng lặp khi join
    df_copy.columns = [f"{col}_{tf_name.upper()}" if col in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME'] else col for col in df_copy.columns]
    return df_copy

def prepare_scalping_data(timeframes_data: Dict[str, pd.DataFrame], strategy_params: Dict) -> Optional[pd.DataFrame]:
    """
    Chuẩn bị dữ liệu cho chiến lược scalping.
    - Base timeframe: M1
    - Execution timeframe: M5
    - Trend timeframe: M15
    """
    required_tfs = ['m1', 'm5', 'm15', 'm30', 'h1', 'h4', 'd1']
    if not all(tf in timeframes_data for tf in ['m1', 'm5', 'm15']):
        print("Lỗi: Thiếu dữ liệu M1, M5, hoặc M15.")
        return None

    # --- 1. Tính toán chỉ báo trên từng khung thời gian ---
    print("Đang tính toán các chỉ báo trên từng khung thời gian...")
    processed_tfs = {}
    for tf in required_tfs:
        if tf in timeframes_data:
            processed_tfs[tf] = _calculate_indicators_for_tf(timeframes_data[tf], tf, strategy_params)

    # --- 2. Hợp nhất tất cả các khung thời gian vào M1 ---
    print("Đang hợp nhất các khung thời gian...")
    # Bắt đầu với M1 gốc (chỉ OHLC)
    merged_df = timeframes_data['m1'].copy()
    merged_df.columns = [col.upper() for col in merged_df.columns]

    for tf_name, tf_df in processed_tfs.items():
        merged_df = merged_df.join(tf_df.reindex(merged_df.index, method='ffill'))

    # --- BỔ SUNG: Tính toán CPR hàng ngày ---
    if 'd1' in timeframes_data:
        print("Calculating CPR levels...")
        cpr_df = _calculate_cpr(timeframes_data['d1'])
        # Resample CPR data to M1 and forward-fill
        cpr_df_resampled = cpr_df.reindex(merged_df.index, method='ffill')
        merged_df = pd.concat([merged_df, cpr_df_resampled], axis=1)

    # --- BỔ SUNG: Tính toán Volume Profile và POC ---
    vp_params = strategy_params.get('CprVolumeProfileStrategy', {})
    vp_width = vp_params.get('vp_width', 20)
    vp_lookback = vp_params.get('vp_lookback', 240) # e.g., 240 bars of M5 data = 2 days

    # Calculate Volume Profile on M5 data
    if 'CLOSE_M5' in merged_df.columns and 'VOLUME_M5' in merged_df.columns:
        print("Calculating Volume Profile and POC...")
        poc_list = []
        for date in pd.Series(merged_df.index.date).unique():
            daily_data = merged_df[merged_df.index.date == date]
            vp = ta.vp(daily_data['CLOSE_M5'], daily_data['VOLUME_M5'], width=vp_width)
            if vp is not None and not vp.empty:
                poc = vp.loc[vp[f'total_{daily_data["VOLUME_M5"].name}'].idxmax()][f'mean_{daily_data["CLOSE_M5"].name}']
                poc_list.append(pd.DataFrame({'POC': poc}, index=daily_data.index))

        if poc_list:
            poc_df = pd.concat(poc_list)
            # SỬA LỖI: Chỉ join nếu poc_df không rỗng
            if not poc_df.empty:
                merged_df = merged_df.join(poc_df)
                merged_df['POC'].ffill(inplace=True) # Forward fill để lấp các giá trị thiếu


    # Lấy tham số từ config
    ema_params = strategy_params.get('ScalpingEmaCrossoverStrategy', {})
    ema_fast_len = ema_params.get('ema_fast_len', 9)
    ema_slow_len = ema_params.get('ema_slow_len', 20)

    # Tính toán chỉ báo trên dữ liệu đã được ffill từ khung thời gian tương ứng
    merged_df[f'M5_EMA_{ema_fast_len}'] = ta.ema(merged_df['CLOSE_M5'], length=ema_fast_len)
    merged_df[f'M5_EMA_{ema_slow_len}'] = ta.ema(merged_df['CLOSE_M5'], length=ema_slow_len)
    merged_df['RSI_14'] = ta.rsi(merged_df['CLOSE_M5'], length=14)
    
    # --- BỔ SUNG: Tính toán ATR trên M5 cho SL động ---
    # Sử dụng HIGH_M5, LOW_M5, CLOSE_M5 để tính ATR
    merged_df['ATR_14_M5'] = ta.atr(high=merged_df['HIGH_M5'], low=merged_df['LOW_M5'], close=merged_df['CLOSE_M5'], length=14)

    merged_df['M15_EMA_34'] = ta.ema(merged_df['CLOSE_M15'], length=34)
    merged_df['M15_EMA_89'] = ta.ema(merged_df['CLOSE_M15'], length=89)
    m15_ema_200 = ta.ema(merged_df['CLOSE_M15'], length=200)
    # Thêm các chỉ báo M15 cần cho XauSmartScalpStrategy
    merged_df['ATR_14_M15'] = ta.atr(high=merged_df['HIGH_M15'], low=merged_df['LOW_M15'], close=merged_df['CLOSE_M15'], length=14)
    merged_df['RSI_14_M15'] = ta.rsi(merged_df['CLOSE_M15'], length=14)

    merged_df['M15_TREND_EMA200'] = np.where(merged_df['CLOSE_M15'] > m15_ema_200, 1, -1)
    
    # Add all available Candlestick Patterns to the merged DataFrame
    merged_df.ta.cdl_pattern(name="all", append=True)

    if 'CLOSE_M30' in merged_df.columns:
        m30_ema_200 = ta.ema(merged_df['CLOSE_M30'], length=200)
        merged_df['M30_TREND'] = np.where(merged_df['CLOSE_M30'] > m30_ema_200, 1, -1)

    if 'CLOSE_H1' in merged_df.columns:
        h1_ema_200 = ta.ema(merged_df['CLOSE_H1'], length=200)
        merged_df['H1_EMA_34'] = ta.ema(merged_df['CLOSE_H1'], length=34)
        merged_df['H1_EMA_89'] = ta.ema(merged_df['CLOSE_H1'], length=89)
        merged_df['H1_ATR_14'] = ta.atr(high=merged_df['HIGH_H1'], low=merged_df['LOW_H1'], close=merged_df['CLOSE_H1'], length=14)
        merged_df['H1_TREND'] = np.where(merged_df['CLOSE_H1'] > h1_ema_200, 1, -1)

    if 'CLOSE_D1' in merged_df.columns:
        d1_ema_200 = ta.ema(merged_df['CLOSE_D1'], length=200)
        merged_df['D1_EMA_34'] = ta.ema(merged_df['CLOSE_D1'], length=34)
        merged_df['D1_EMA_89'] = ta.ema(merged_df['CLOSE_D1'], length=89)
        merged_df['D1_TREND'] = np.where(merged_df['CLOSE_D1'] > d1_ema_200, 1, -1)
        
    # --- BỔ SUNG TÍNH TOÁN ADX CHO M15 FILTER ---
    # Lấy adx_length từ config, nếu không có thì lấy trong M15FilteredScalpingStrategy, mặc định là 14
    m15_filter_params = strategy_params.get('M15FilteredScalpingStrategy', {})
    adx_length = m15_filter_params.get('adx_length', 14)
    adx_col_name = f'ADX_{adx_length}'
    adx_m15_col_name = f'ADX_{adx_length}_M15'
    
    if 'HIGH_M15' in merged_df.columns and 'LOW_M15' in merged_df.columns and 'CLOSE_M15' in merged_df.columns:
        print(f"Calculating {adx_col_name} on M15 data...")
        adx_indicator = ta.adx(high=merged_df['HIGH_M15'], low=merged_df['LOW_M15'], close=merged_df['CLOSE_M15'], length=adx_length)
        if adx_col_name in adx_indicator.columns:
            merged_df[adx_m15_col_name] = adx_indicator[adx_col_name]
            
    # --- BỔ SUNG TÍNH TOÁN S/R CHO XauSmartScalpStrategy ---
    sr_periods = {'m15': 50, 'h1': 50, 'h4': 50} # Ví dụ, có thể tinh chỉnh
    for tf_name, period in sr_periods.items():
        tf_upper = tf_name.upper()
        if f'HIGH_{tf_upper}' in merged_df.columns:
            merged_df[f'{tf_upper}_S'] = merged_df[f'LOW_{tf_upper}'].rolling(window=period, min_periods=1).min()
            merged_df[f'{tf_upper}_R'] = merged_df[f'HIGH_{tf_upper}'].rolling(window=period, min_periods=1).max()

    # --- 3. Dọn dẹp dữ liệu ---
    # Giữ lại các cột OHLC của M1 (gốc) và M5 (cho tính toán scalping)
    # Xóa các cột OHLC không cần thiết khác để làm sạch
    # SỬA LỖI: Giữ lại các cột của M15 vì chúng cần thiết cho việc tính toán chỉ báo của chiến lược (ví dụ ADX_M15).
    # Chỉ xóa các cột của H1, H4, D1, v.v.
    cols_to_drop = [col for col in merged_df.columns if any(s in col for s in ['OPEN_', 'HIGH_', 'LOW_', 'CLOSE_', 'VOLUME_']) and not any(s in col for s in ['_M5', '_M15'])]
    # Giữ lại các cột gốc của M1 không có hậu tố
    # cols_to_drop = [c for c in cols_to_drop if c not in ['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']] # Dòng này không cần thiết và có thể gây lỗi
    merged_df.drop(columns=cols_to_drop, inplace=True, errors='ignore')

    merged_df.dropna(inplace=True)

    print("Chuẩn bị dữ liệu scalping hoàn tất.")
    return merged_df
