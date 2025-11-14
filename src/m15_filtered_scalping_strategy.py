# -*- coding: utf-8 -*-
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
        # Cải tiến 1: Thêm ngưỡng trễ (Hysteresis)
        self.adx_hysteresis = filter_params.get('adx_hysteresis', 2.0)
        # Cải tiến 3: Thêm bộ lọc xác nhận từ khung thời gian cao hơn
        self.htf_trend_score_threshold = filter_params.get('htf_trend_score_threshold', 2)
        # Cải tiến 4: Thêm Bộ lọc khối lượng
        self.volume_filter_enabled = filter_params.get('volume_filter_enabled', True)
        self.volume_ma_period = filter_params.get('volume_ma_period', 20)
        self.volume_factor = filter_params.get('volume_factor', 0.8)
        # Cải tiến 5: Thêm bộ lọc RSI trên M15
        self.m15_rsi_filter_enabled = filter_params.get('m15_rsi_filter_enabled', True)
        self.m15_rsi_period = filter_params.get('m15_rsi_period', 14)
        self.m15_rsi_ob = filter_params.get('m15_rsi_ob', 70)
        self.m15_rsi_os = filter_params.get('m15_rsi_os', 30)

        # Khởi tạo các chiến lược con với đúng khối tham số của chúng
        self.trend_strategy = CombinedScalpingStrategy(self.params.get('CombinedScalpingStrategy', {}))
        self.range_strategy = BollingerBandMeanReversionStrategy(self.params.get('BollingerBandMeanReversionStrategy', {}))

        # Biến trạng thái để lưu chế độ thị trường hiện tại (Trend, Range, Chop)
        self.current_mode = "Chop" # Khởi tạo ở trạng thái không giao dịch

    def _check_htf_confluence(self, latest_data):
        """
        Cải tiến 3: Tính toán "Điểm số xu hướng" (Trend Score) từ các khung M15, H1, H4.
        - Trả về điểm số: +1 cho mỗi khung thời gian tăng, -1 cho mỗi khung giảm.
        - Tổng điểm có thể từ -3 đến +3.
        """
        trend_score = 0
        required_cols = ['M15_EMA_34', 'M15_EMA_89', 'H1_EMA_34', 'H1_EMA_89', 'H4_EMA_34', 'H4_EMA_89']
        if not all(col in latest_data for col in required_cols):
            print("Cảnh báo: Thiếu dữ liệu EMA đa khung thời gian để tính điểm xu hướng.")
            return 0

        # M15 Trend
        if latest_data['M15_EMA_34'] > latest_data['M15_EMA_89']:
            trend_score += 1
        else:
            trend_score -= 1

        # H1 Trend
        if latest_data['H1_EMA_34'] > latest_data['H1_EMA_89']:
            trend_score += 1
        else:
            trend_score -= 1

        # H4 Trend
        if latest_data['H4_EMA_34'] > latest_data['H4_EMA_89']:
            trend_score += 1
        else:
            trend_score -= 1
            
        return trend_score

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

        # --- 2. Cải tiến 1: Xác định chế độ thị trường với Ngưỡng trễ (Hysteresis) ---
        # Logic chuyển đổi chế độ mượt mà hơn
        if self.current_mode == "Trend-Following":
            # Nếu đang trong chế độ Trend, chỉ chuyển sang Chop khi ADX giảm xuống dưới ngưỡng range
            if m15_adx < self.adx_range_threshold:
                self.current_mode = "Chop"
        elif self.current_mode == "Mean-Reversion":
            # Nếu đang trong chế độ Range, chỉ chuyển sang Trend khi ADX vượt lên trên ngưỡng trend
            if m15_adx > self.adx_trend_threshold:
                self.current_mode = "Trend-Following"
        else: # self.current_mode == "Chop"
            # Nếu đang ở vùng không rõ ràng, kiểm tra để chuyển sang chế độ phù hợp
            if m15_adx >= self.adx_trend_threshold + self.adx_hysteresis:
                self.current_mode = "Trend-Following"
            elif m15_adx <= self.adx_range_threshold - self.adx_hysteresis:
                self.current_mode = "Mean-Reversion"

        # --- 3. Chọn chiến lược phù hợp dựa trên chế độ đã xác định ---
        signal, sl, tp = 0, None, None
        strategy_used_name = "None"

        # Kịch bản 1: Thị trường có xu hướng mạnh
        if self.current_mode == "Trend-Following":
            strategy_used_name = "Trend-Following"
            print(f"Chế độ {strategy_used_name} (ADX M15 = {m15_adx:.2f})")
            
            # Lấy tín hiệu từ chiến lược theo xu hướng
            raw_signal, sl, tp = self.trend_strategy.get_signal(analyzed_data)
            
            # Áp dụng các bộ lọc nếu có tín hiệu
            if raw_signal != 0:
                signal = raw_signal # Giả định tín hiệu hợp lệ ban đầu

                # --- Filter 1: Cross-Strategy Veto ---
                veto_signal, _, _ = self.range_strategy.get_signal(analyzed_data)
                if veto_signal == -signal:
                    print(f"Tín hiệu {strategy_used_name} bị hủy do có tín hiệu đối nghịch từ Mean-Reversion.")
                    signal = 0

                # --- Filter 2: HTF Confluence ---
                if signal != 0:
                    trend_score = self._check_htf_confluence(latest)
                    is_buy_ok = (signal == 1 and trend_score >= self.htf_trend_score_threshold)
                    is_sell_ok = (signal == -1 and trend_score <= -self.htf_trend_score_threshold)
                    if not (is_buy_ok or is_sell_ok):
                        print(f"Tín hiệu {strategy_used_name} bị hủy do không đủ đồng thuận HTF. Điểm: {trend_score}")
                        signal = 0

                # --- Filter 3: Volume Confirmation ---
                if signal != 0 and self.volume_filter_enabled:
                    volume_ma_col = f'volume_ma_{self.volume_ma_period}'
                    current_volume = latest.get('tick_volume')
                    avg_volume = latest.get(volume_ma_col)
                    if current_volume is None or avg_volume is None or pd.isna(current_volume) or pd.isna(avg_volume):
                        print("Cảnh báo: Không có dữ liệu khối lượng để lọc.")
                    elif current_volume < avg_volume * self.volume_factor:
                        print(f"Tín hiệu {strategy_used_name} bị hủy do khối lượng thấp. KL: {current_volume:.0f} < MA({self.volume_ma_period}): {avg_volume:.0f}")
                        signal = 0
                
                # --- Filter 4: M15 RSI ---
                if signal != 0 and self.m15_rsi_filter_enabled:
                    rsi_col = f'M15_RSI_{self.m15_rsi_period}'
                    m15_rsi = latest.get(rsi_col)
                    if m15_rsi is None or pd.isna(m15_rsi):
                        print("Cảnh báo: Không có dữ liệu RSI M15 để lọc.")
                    elif signal == 1 and m15_rsi > self.m15_rsi_ob:
                        print(f"Tín hiệu MUA bị hủy do RSI M15 quá mua. RSI: {m15_rsi:.2f} > {self.m15_rsi_ob}")
                        signal = 0
                    elif signal == -1 and m15_rsi < self.m15_rsi_os:
                        print(f"Tín hiệu BÁN bị hủy do RSI M15 quá bán. RSI: {m15_rsi:.2f} < {self.m15_rsi_os}")
                        signal = 0

        # Kịch bản 2: Thị trường đi ngang (ranging)
        elif self.current_mode == "Mean-Reversion":
            strategy_used_name = "Mean-Reversion"
            print(f"Chế độ {strategy_used_name} (ADX M15 = {m15_adx:.2f})")
            
            # Lấy tín hiệu từ chiến lược đảo chiều
            signal, sl, tp = self.range_strategy.get_signal(analyzed_data)

        # Kịch bản 3: Thị trường không rõ ràng (ADX ở giữa)
        else:
            print(f"Thị trường không rõ ràng (Chế độ: {self.current_mode}, ADX M15 = {m15_adx:.2f}). Không giao dịch.")
            return 0, None, None

        if signal != 0:
            print(f"Tín hiệu được xác nhận từ chế độ {strategy_used_name}: {'BUY' if signal == 1 else 'SELL'}")
            return signal, sl, tp

        return 0, None, None # Không có tín hiệu từ chiến lược con