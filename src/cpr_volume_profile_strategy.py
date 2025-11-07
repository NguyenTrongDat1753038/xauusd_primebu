
from .base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class CprVolumeProfileStrategy(BaseStrategy):
    """
    A strategy based on Central Pivot Range (CPR), Volume Profile, and Point of Control (POC),
    with added RSI and Trend filters.
    """
    def __init__(self, params):
        super().__init__(params)
        self.atr_multiplier_sl = params.get('atr_multiplier_sl', 1.5)
        self.rr_ratio = params.get('rr_ratio', 2.0)
        self.poc_retest_tolerance = params.get('poc_retest_tolerance', 0.001) # 0.1%
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.use_strict_trend_filter = params.get('use_strict_trend_filter', False)

        self.bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        self.bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']


    def get_signal(self, data):
        """
        Generates a trading signal based on the strategy.
        :param data: DataFrame with market data and indicators.
        :return: 1 for buy, -1 for sell, 0 for no signal, sl, tp.
        """
        if len(data) < 2:
            return 0, None, None

        latest = data.iloc[-1]
        entry_price = latest['CLOSE_M5']

        # --- 1. Get indicators ---
        cpr_pivot = latest.get('CPR_PIVOT')
        cpr_bc = latest.get('CPR_BC')
        cpr_tc = latest.get('CPR_TC')
        poc = latest.get('POC')
        atr = latest.get('ATR_14_M15')
        rsi_m15 = latest.get('RSI_14_M15')
        h4_trend = latest.get('H4_TREND', 0)

        if any(pd.isna(v) for v in [cpr_pivot, cpr_bc, cpr_tc, poc, atr, rsi_m15]):
            return 0, None, None

        # --- 2. Candlestick Confirmation ---
        is_bullish_candle = any(latest.get(p, 0) > 0 for p in self.bullish_patterns)
        is_bearish_candle = any(latest.get(p, 0) < 0 for p in self.bearish_patterns)

        # --- 3. Entry Logic ---
        signal = 0

        # BUY Signal: Price above CPR, pulls back to POC, bullish candle, RSI not overbought, and optional trend filter.
        if entry_price > cpr_tc and abs(latest['LOW_M5'] - poc) / poc < self.poc_retest_tolerance and is_bullish_candle:
            if rsi_m15 < self.rsi_overbought:
                if self.use_strict_trend_filter and h4_trend == -1:
                    pass # Strict mode: No BUY in H4 downtrend
                else:
                    signal = 1
                    print(f"BUY Signal: CPR/POC retest, RSI={rsi_m15:.1f}, H4 Trend={h4_trend}")

        # SELL Signal: Price below CPR, pulls back to POC, bearish candle, RSI not oversold, and optional trend filter.
        elif entry_price < cpr_bc and abs(latest['HIGH_M5'] - poc) / poc < self.poc_retest_tolerance and is_bearish_candle:
            if rsi_m15 > self.rsi_oversold:
                if self.use_strict_trend_filter and h4_trend == 1:
                    pass # Strict mode: No SELL in H4 uptrend
                else:
                    signal = -1
                    print(f"SELL Signal: CPR/POC retest, RSI={rsi_m15:.1f}, H4 Trend={h4_trend}")

        # --- 4. Exit Logic ---
        if signal != 0:
            sl_distance = atr * self.atr_multiplier_sl
            tp_distance = sl_distance * self.rr_ratio

            if signal == 1: # BUY
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + tp_distance
            else: # SELL
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - tp_distance
            
            return signal, stop_loss, take_profit

        return 0, None, None
