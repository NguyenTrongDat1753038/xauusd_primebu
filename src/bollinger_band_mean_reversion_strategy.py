from .base_strategy import BaseStrategy # Giữ nguyên import tương đối
import pandas as pd

class BollingerBandMeanReversionStrategy(BaseStrategy):
    """
    Chiến lược Mean Reversion dựa trên Bollinger Bands và RSI.
    - MUA khi giá chạm dải dưới BB và RSI quá bán.
    - BÁN khi giá chạm dải trên BB và RSI quá mua.
    """
    def __init__(self, params):
        super().__init__(params)
        self.bb_length = params.get('bb_length', 20)
        self.bb_std_dev = params.get('bb_std_dev', 2.0) # Ensure float for column name
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.swing_lookback = params.get('swing_lookback', 10) # Tìm đỉnh/đáy cho SL
        self.rr_ratio = params.get('rr_ratio', 1.5) # Tỷ lệ Risk/Reward

    def get_signal(self, analyzed_data: pd.DataFrame) -> tuple[int, float | None, float | None]:
        if len(analyzed_data) < self.bb_length:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        entry_price = latest.get('CLOSE_M5', latest.get('CLOSE')) # Sử dụng giá M5 cho chiến lược scalping

        # Lấy các chỉ báo đã được tính toán trong analysis.py
        bb_upper_col = f'BBU_{self.bb_length}_{self.bb_std_dev}'
        bb_lower_col = f'BBL_{self.bb_length}_{self.bb_std_dev}'
        bb_upper = latest.get(bb_upper_col)
        bb_lower = latest.get(bb_lower_col)
        rsi = latest.get('RSI_14_M5') # Use M5 RSI

        if any(v is None or pd.isna(v) for v in [bb_upper, bb_lower, rsi]):
            return 0, None, None

        # Tín hiệu MUA: Giá chạm dải dưới BB và RSI quá bán
        if entry_price <= bb_lower and rsi < self.rsi_oversold:
            recent_low = analyzed_data['LOW_M5'].iloc[-self.swing_lookback:].min()
            stop_loss = recent_low - 0.2 # Thêm một khoảng đệm nhỏ
            sl_distance = entry_price - stop_loss
            if sl_distance <= 0: return 0, None, None
            take_profit = entry_price + (sl_distance * self.rr_ratio)
            return 1, stop_loss, take_profit

        # Tín hiệu BÁN: Giá chạm dải trên BB và RSI quá mua
        if entry_price >= bb_upper and rsi > self.rsi_overbought:
            recent_high = analyzed_data['HIGH_M5'].iloc[-self.swing_lookback:].max()
            stop_loss = recent_high + 0.2 # Thêm một khoảng đệm nhỏ
            sl_distance = stop_loss - entry_price
            if sl_distance <= 0: return 0, None, None
            take_profit = entry_price - (sl_distance * self.rr_ratio)
            return -1, stop_loss, take_profit

        return 0, None, None # Không có tín hiệu