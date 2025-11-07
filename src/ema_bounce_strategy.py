
from .base_strategy import BaseStrategy
import pandas as pd

class EmaBounceStrategy(BaseStrategy):
    """
    A strategy based on price bouncing off key EMA levels, with RSI and trend filters.
    """
    def __init__(self, params):
        super().__init__(params)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.atr_multiplier_sl = params.get('atr_multiplier_sl', 1.5)
        self.rr_ratio = params.get('rr_ratio', 2.0)
        self.use_strict_trend_filter = params.get('use_strict_trend_filter', False)
        self.ema_retest_tolerance = params.get('ema_retest_tolerance', 0.001) # 0.1%

        self.bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        self.bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']
        
        self.emas_to_check = [
            'M15_EMA_34', 'M15_EMA_89', 'M15_EMA_200',
            'H1_EMA_34', 'H1_EMA_89', 'H1_EMA_200',
            'H4_EMA_34', 'H4_EMA_89', 'H4_EMA_200',
        ]

    def get_signal(self, data):
        if len(data) < 2:
            return 0, None, None

        latest = data.iloc[-1]
        entry_price = latest['CLOSE_M15']

        # --- 1. Indicators ---
        h4_trend = latest.get('H4_TREND', 0)
        rsi_m15 = latest.get('RSI_14_M15')
        atr_m15 = latest.get('ATR_14_M15')

        if any(pd.isna(v) for v in [rsi_m15, atr_m15]):
            return 0, None, None

        # --- 2. Candlestick Confirmation ---
        is_bullish_candle = any(latest.get(p, 0) > 0 for p in self.bullish_patterns)
        is_bearish_candle = any(latest.get(p, 0) < 0 for p in self.bearish_patterns)

        # --- 3. Entry Logic ---
        signal = 0

        # BUY Signal: Price bounces off an EMA from above.
        if is_bullish_candle and rsi_m15 < self.rsi_overbought:
            if not (self.use_strict_trend_filter and h4_trend == -1):
                for ema_col in self.emas_to_check:
                    ema_value = latest.get(ema_col)
                    if ema_value and not pd.isna(ema_value):
                        # Check if the low of the candle touched the EMA
                        if latest['LOW_M15'] <= ema_value * (1 + self.ema_retest_tolerance) and latest['CLOSE_M15'] > ema_value:
                            signal = 1
                            print(f"BUY Signal: Bounce off {ema_col} at {ema_value:.2f}, RSI={rsi_m15:.1f}")
                            break # Found a signal, no need to check other EMAs

        # SELL Signal: Price bounces off an EMA from below.
        if signal == 0 and is_bearish_candle and rsi_m15 > self.rsi_oversold:
            if not (self.use_strict_trend_filter and h4_trend == 1):
                for ema_col in self.emas_to_check:
                    ema_value = latest.get(ema_col)
                    if ema_value and not pd.isna(ema_value):
                        # Check if the high of the candle touched the EMA
                        if latest['HIGH_M15'] >= ema_value * (1 - self.ema_retest_tolerance) and latest['CLOSE_M15'] < ema_value:
                            signal = -1
                            print(f"SELL Signal: Bounce off {ema_col} at {ema_value:.2f}, RSI={rsi_m15:.1f}")
                            break # Found a signal, no need to check other EMAs

        # --- 4. Exit Logic ---
        if signal != 0:
            sl_distance = atr_m15 * self.atr_multiplier_sl
            tp_distance = sl_distance * self.rr_ratio

            if signal == 1: # BUY
                stop_loss = entry_price - sl_distance
                take_profit = entry_price + tp_distance
            else: # SELL
                stop_loss = entry_price + sl_distance
                take_profit = entry_price - tp_distance
            
            return signal, stop_loss, take_profit

        return 0, None, None
