import pandas as pd
from .base_strategy import BaseStrategy

class ScalpingEmaCrossoverStrategy(BaseStrategy):
    """
    Chiến lược Scalping dựa trên sự giao cắt của các đường EMA trên khung thời gian thấp,
    được lọc bởi xu hướng trên khung thời gian cao hơn.
    - Khung xu hướng: M15 (EMA 200)
    - Khung vào lệnh: M5 (EMA 9 cắt EMA 20)
    """
    def __init__(self, params):
        super().__init__(params)
        self.ema_fast_len = params.get('ema_fast_len', 9)
        self.ema_slow_len = params.get('ema_slow_len', 20)
        self.swing_lookback = params.get('swing_lookback', 10) # Tìm đỉnh/đáy trong 10 nến gần nhất
        self.rr_ratio = params.get('rr_ratio', 1.5) # Tỷ lệ Risk/Reward
        self.use_atr_sl = params.get('use_atr_sl', False)
        self.atr_multiplier = params.get('atr_multiplier', 1.5)

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2] # Nến ngay trước đó

        m15_trend = latest.get('M15_TREND_EMA200', 0)
        entry_price = latest['CLOSE_M5'] # Sử dụng giá M5
        
        ema_fast_latest = latest.get(f'M5_EMA_{self.ema_fast_len}')
        ema_slow_latest = latest.get(f'M5_EMA_{self.ema_slow_len}')
        ema_fast_previous = previous.get(f'M5_EMA_{self.ema_fast_len}')
        ema_slow_previous = previous.get(f'M5_EMA_{self.ema_slow_len}')
        
        if any(v is None for v in [ema_fast_latest, ema_slow_latest, ema_fast_previous, ema_slow_previous]):
            return 0, None, None

        # Tín hiệu MUA: Xu hướng M15 tăng VÀ EMA nhanh cắt lên EMA chậm
        if m15_trend == 1 and ema_fast_previous < ema_slow_previous and ema_fast_latest > ema_slow_latest:
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

        # Tín hiệu BÁN: Xu hướng M15 giảm VÀ EMA nhanh cắt xuống EMA chậm
        if m15_trend == -1 and ema_fast_previous > ema_slow_previous and ema_fast_latest < ema_slow_latest:
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