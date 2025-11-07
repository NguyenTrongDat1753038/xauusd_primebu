from .base_strategy import BaseStrategy
from .combined_strategy import CombinedScalpingStrategy
from .bollinger_band_mean_reversion_strategy import BollingerBandMeanReversionStrategy
import pandas as pd

class M15FilteredScalpingStrategy(BaseStrategy):
    """
    Chiến lược này tự động chuyển đổi giữa scalping theo xu hướng và đảo chiều trên M5,
    dựa trên trạng thái thị trường được xác định bởi chỉ báo ADX trên M15.

    - Khi ADX cao (Thị trường có xu hướng): Kích hoạt chế độ Trend-Following (CombinedScalpingStrategy).
    - Khi ADX thấp (Thị trường đi ngang): Kích hoạt chế độ Mean-Reversion (BollingerBandMeanReversionStrategy).
    """
    def __init__(self, params):
        # `params` ở đây là toàn bộ mục "strategy" từ config
        super().__init__(params)
        
        # Lấy các tham số chung cho bộ lọc
        filter_params = self.params # params được truyền vào đã là khối M15FilteredScalpingStrategy
        self.adx_length = filter_params.get('adx_length', 14)
        self.adx_trend_threshold = filter_params.get('adx_trend_threshold', 25)
        self.adx_range_threshold = filter_params.get('adx_range_threshold', 20)
        
        # Khởi tạo các chiến lược con với đúng khối tham số của chúng
        self.trend_strategy = CombinedScalpingStrategy(self.params.get('CombinedScalpingStrategy', {}))
        self.range_strategy = BollingerBandMeanReversionStrategy(self.params.get('BollingerBandMeanReversionStrategy', {}))

    def get_signal(self, analyzed_data):
        """
        Kiểm tra trạng thái thị trường bằng ADX và gọi chiến lược con phù hợp.
        """
        if len(analyzed_data) < 2 or analyzed_data.empty:
            return 0, None, None

        latest = analyzed_data.iloc[-1]

        # --- 1. Phát hiện trạng thái thị trường bằng ADX M15 ---
        m15_adx = latest.get(f'ADX_{self.adx_length}_M15')
        if m15_adx is None or pd.isna(m15_adx):
            print("Cảnh báo: Không tìm thấy giá trị ADX M15.")
            return 0, None, None

        # --- 2. Chọn chiến lược phù hợp ---
        signal, sl, tp = 0, None, None
        strategy_used_name = "None"

        # Kịch bản 1: Thị trường có xu hướng mạnh
        if m15_adx >= self.adx_trend_threshold:
            strategy_used_name = "Trend-Following"
            print(f"Chế độ {strategy_used_name} (ADX M15 = {m15_adx:.2f} >= {self.adx_trend_threshold})")
            
            # Lấy tín hiệu từ chiến lược theo xu hướng
            raw_signal, sl, tp = self.trend_strategy.get_signal(analyzed_data)
            
            # BỘ LỌC BỔ SUNG: Đảm bảo tín hiệu M5 phù hợp với xu hướng M15
            m15_ema_34 = latest.get('M15_EMA_34')
            m15_ema_89 = latest.get('M15_EMA_89')
            if m15_ema_34 is not None and m15_ema_89 is not None:
                is_m15_uptrend = (m15_ema_34 > m15_ema_89)
                
                # SỬA LỖI LOGIC: Chỉ chấp nhận tín hiệu MUA khi M15 tăng và ngược lại
                if (raw_signal == 1 and is_m15_uptrend) or \
                   (raw_signal == -1 and not is_m15_uptrend):
                    signal = raw_signal # Tín hiệu hợp lệ, chấp nhận
                else:
                    print(f"Tín hiệu {strategy_used_name} bị hủy do không cùng pha với xu hướng M15 (Signal: {raw_signal}, M15 Trend Up: {is_m15_uptrend}).")
                    signal = 0 # Hủy tín hiệu nếu không cùng pha

        # Kịch bản 2: Thị trường đi ngang (ranging)
        elif m15_adx <= self.adx_range_threshold:
            strategy_used_name = "Mean-Reversion"
            print(f"Chế độ {strategy_used_name} (ADX M15 = {m15_adx:.2f} <= {self.adx_range_threshold})")
            
            # Lấy tín hiệu từ chiến lược đảo chiều
            signal, sl, tp = self.range_strategy.get_signal(analyzed_data)

        # Kịch bản 3: Thị trường không rõ ràng (ADX ở giữa)
        else:
            print(f"Thị trường không rõ ràng (ADX M15 = {m15_adx:.2f}). Không giao dịch.")
            return 0, None, None

        if signal != 0:
            print(f"Tín hiệu được xác nhận từ chế độ {strategy_used_name}: {'BUY' if signal == 1 else 'SELL'}")
            return signal, sl, tp

        return 0, None, None # Không có tín hiệu từ chiến lược con