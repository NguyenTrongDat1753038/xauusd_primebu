import pandas as pd
import pandas_ta as ta

def resample_data(data, timeframe):
    """Resamples OHLCV data to a different timeframe."""
    resampled = data.resample(timeframe).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'tick_volume': 'sum'
    }).dropna()
    return resampled

def calculate_indicators(data, params):
    """
    Calculates all necessary indicators for the given data and parameters.
    This function will be the core of feature engineering.
    """
    # Ensure data index is datetime
    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)

    # --- 1. Base M5 Indicators ---
    m5_data = data.copy()
    # Cải tiến 4: Thêm bộ lọc khối lượng
    volume_ma_period = params.get('M15FilteredScalpingStrategy', {}).get('volume_ma_period', 20)
    m5_data[f'volume_ma_{volume_ma_period}'] = m5_data['tick_volume'].rolling(window=volume_ma_period).mean()


    # --- 2. M15 Indicators ---
    m15_data = resample_data(data, '15min')
    filter_params = params.get('M15FilteredScalpingStrategy', {})
    adx_length = filter_params.get('adx_length', 14)
    m15_rsi_period = filter_params.get('m15_rsi_period', 14)

    m15_data.ta.adx(length=adx_length, append=True)
    m15_data.ta.ema(length=34, append=True)
    m15_data.ta.ema(length=89, append=True)
    # Cải tiến 5: Thêm bộ lọc RSI trên M15
    m15_data.ta.rsi(length=m15_rsi_period, append=True)
    
    m15_data = m15_data[[f'ADX_{adx_length}', 'EMA_34', 'EMA_89', f'RSI_{m15_rsi_period}']]
    m15_data.columns = [f'ADX_{adx_length}_M15', 'M15_EMA_34', 'M15_EMA_89', f'M15_RSI_{m15_rsi_period}']

    # --- 3. H1 Indicators ---
    h1_data = resample_data(data, '1H')
    h1_data.ta.ema(length=34, append=True)
    h1_data.ta.ema(length=89, append=True)
    h1_data = h1_data[['EMA_34', 'EMA_89']]
    h1_data.columns = ['H1_EMA_34', 'H1_EMA_89']

    # --- 4. H4 Indicators ---
    h4_data = resample_data(data, '4H')
    h4_data.ta.ema(length=34, append=True)
    h4_data.ta.ema(length=89, append=True)
    h4_data = h4_data[['EMA_34', 'EMA_89']]
    h4_data.columns = ['H4_EMA_34', 'H4_EMA_89']

    # --- 5. Merge all dataframes ---
    # Merge M15 indicators into M5 data
    merged_data = pd.merge_asof(m5_data.sort_index(), m15_data.sort_index(), 
                                left_index=True, right_index=True, 
                                direction='forward')
    
    # Merge H1 indicators
    merged_data = pd.merge_asof(merged_data.sort_index(), h1_data.sort_index(), 
                                left_index=True, right_index=True, 
                                direction='forward')

    # Merge H4 indicators
    merged_data = pd.merge_asof(merged_data.sort_index(), h4_data.sort_index(), 
                                left_index=True, right_index=True, 
                                direction='forward')

    # Let sub-strategies calculate their own primary indicators on the merged data
    # This ensures they have access to the HTF data as well.
    trend_params = params.get('M15FilteredScalpingStrategy', {}).get('CombinedScalpingStrategy', {})
    range_params = params.get('M15FilteredScalpingStrategy', {}).get('BollingerBandMeanReversionStrategy', {})

    # CombinedScalpingStrategy indicators
    if trend_params:
        merged_data.ta.ema(length=trend_params.get('ema_short_period', 5), append=True)
        merged_data.ta.ema(length=trend_params.get('ema_long_period', 15), append=True)
        merged_data.ta.rsi(length=trend_params.get('rsi_period', 14), append=True)
        merged_data.ta.adx(length=trend_params.get('adx_period', 14), append=True)

    # BollingerBandMeanReversionStrategy indicators
    if range_params:
        merged_data.ta.bbands(length=range_params.get('bb_length', 20), std=range_params.get('bb_std', 2), append=True)
        merged_data.ta.rsi(length=range_params.get('rsi_period', 14), append=True) # Avoid re-calculation if already present

    return merged_data.dropna()
