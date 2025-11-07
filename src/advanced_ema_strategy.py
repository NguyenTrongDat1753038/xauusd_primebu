
from .base_strategy import BaseStrategy
import pandas as pd

class AdvancedEmaStrategy(BaseStrategy):
    """
    A strategy based on EMA crossovers, trend filters, and RSI.
    Phase 1: Core EMA Crossover Logic with H4 Trend and RSI Filter.
    """
    def __init__(self, params):
        super().__init__(params)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.atr_multiplier_sl = params.get('atr_multiplier_sl', 1.5)
        self.rr_ratio = params.get('rr_ratio', 2.0)
        self.use_strict_trend_filter = params.get('use_strict_trend_filter', False)

    def get_signal(self, data):
        if len(data) < 2:
            return 0, None, None

        latest = data.iloc[-1]
        previous = data.iloc[-2]
        entry_price = latest['CLOSE_M15']

        # --- 1. Indicators ---
        h4_trend = latest.get('H4_TREND', 0)
        rsi_m15 = latest.get('RSI_14_M15')
        atr_m15 = latest.get('ATR_14_M15')

        ema34_m15_latest = latest.get('M15_EMA_34')
        ema89_m15_latest = latest.get('M15_EMA_89')
        ema34_m15_previous = previous.get('M15_EMA_34')
        ema89_m15_previous = previous.get('M15_EMA_89')

        if any(pd.isna(v) for v in [h4_trend, rsi_m15, atr_m15, ema34_m15_latest, ema89_m15_latest, ema34_m15_previous, ema89_m15_previous]):
            return 0, None, None

        # --- 2. Crossover Signals ---
        buy_crossover = ema34_m15_previous < ema89_m15_previous and ema34_m15_latest > ema89_m15_latest
        sell_crossover = ema34_m15_previous > ema89_m15_previous and ema34_m15_latest < ema89_m15_latest

        signal = 0

        # --- 3. Entry Logic ---
        if buy_crossover and rsi_m15 < self.rsi_overbought:
            if self.use_strict_trend_filter and h4_trend == -1:
                pass # Strict mode: No BUY in H4 downtrend
            else:
                signal = 1
                print(f"BUY Signal: EMA Crossover, RSI={rsi_m15:.1f}, H4 Trend={h4_trend}")

        elif sell_crossover and rsi_m15 > self.rsi_oversold:
            if self.use_strict_trend_filter and h4_trend == 1:
                pass # Strict mode: No SELL in H4 uptrend
            else:
                signal = -1
                print(f"SELL Signal: EMA Crossover, RSI={rsi_m15:.1f}, H4 Trend={h4_trend}")

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
