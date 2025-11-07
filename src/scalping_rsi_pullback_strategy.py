import pandas as pd
from .base_strategy import BaseStrategy # Giữ nguyên vì đây là import tương đối trong cùng package

class ScalpingRsiPullbackStrategy(BaseStrategy):
    """
    Chiến lược Scalping dựa trên việc bắt pullback về vùng quá mua/bán của RSI.
    - Khung xu hướng: M15 (EMA 200)
    - Khung vào lệnh: M5 (RSI < 30 cho Mua, RSI > 70 cho Bán)
    """
    def __init__(self, params):
        super().__init__(params)
        self.swing_lookback = params.get('swing_lookback', 10)
        self.rr_ratio = params.get('rr_ratio', 1.5)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.use_atr_sl = params.get('use_atr_sl', False)
        self.atr_multiplier = params.get('atr_multiplier', 1.5)

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2]
        
        m15_trend = latest.get('M15_TREND_EMA200', 0)
        entry_price = latest['CLOSE_M5']

        rsi_latest = latest.get('RSI_14')
        rsi_previous = previous.get('RSI_14')

        if rsi_latest is None or rsi_previous is None:
            return 0, None, None

        # Tín hiệu MUA: Xu hướng M15 tăng VÀ RSI vừa thoát khỏi vùng quá bán
        if m15_trend == 1 and rsi_previous < self.rsi_oversold and rsi_latest > self.rsi_oversold:
            print(f"Tín hiệu MUA: RSI thoát khỏi vùng quá bán ({rsi_previous:.2f} -> {rsi_latest:.2f})")
            recent_low = analyzed_data['LOW_M5'].iloc[-self.swing_lookback:].min()
            if self.use_atr_sl:
                atr = latest.get('ATR_14_M5', 0.2)
                if atr is None or atr <= 0: atr = 0.2
                sl_buffer = atr * self.atr_multiplier
                stop_loss = recent_low - sl_buffer
            else:
                stop_loss = recent_low - 0.2

            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * self.rr_ratio)
            return 1, stop_loss, take_profit

        # Tín hiệu BÁN: Xu hướng M15 giảm VÀ RSI vừa thoát khỏi vùng quá mua
        if m15_trend == -1 and rsi_previous > self.rsi_overbought and rsi_latest < self.rsi_overbought:
            print(f"Tín hiệu BÁN: RSI thoát khỏi vùng quá mua ({rsi_previous:.2f} -> {rsi_latest:.2f})")
            recent_high = analyzed_data['HIGH_M5'].iloc[-self.swing_lookback:].max()
            if self.use_atr_sl:
                atr = latest.get('ATR_14_M5', 0.2)
                if atr is None or atr <= 0: atr = 0.2
                sl_buffer = atr * self.atr_multiplier
                stop_loss = recent_high + sl_buffer
            else:
                stop_loss = recent_high + 0.2

            sl_distance = stop_loss - entry_price
            take_profit = entry_price - (sl_distance * self.rr_ratio)
            return -1, stop_loss, take_profit

        return 0, None, None