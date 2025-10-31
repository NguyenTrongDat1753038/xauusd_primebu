from strategies import BaseStrategy
from combined_strategy import CombinedScalpingStrategy
from strategies import BollingerBandMeanReversionStrategy # Import chiến lược mean reversion mới


class M15FilteredScalpingStrategy(BaseStrategy):
    """
    Một chiến lược bao bọc (wrapper) để lọc các tín hiệu scalping từ CombinedScalpingStrategy
    dựa trên sức mạnh xu hướng của biểu đồ M15.

    Xu hướng M15 được coi là đủ mạnh nếu khoảng cách giữa
    EMA 34 và EMA 89 lớn hơn một ngưỡng đã định cấu hình.

    Nó cũng kiểm tra sự đồng thuận của xu hướng: đối với tín hiệu MUA, cả hai EMA M15
    phải nằm trên EMA 200 M15. Đối với tín hiệu BÁN, chúng phải nằm dưới.
    """
    def __init__(self, params):
        """
        Khởi tạo M15FilteredScalpingStrategy.

        Args:
            params (dict): Một từ điển chứa các tham số.
                - 'm15_ema_strength_threshold' (float): Chênh lệch giá tối thiểu
                  (ví dụ: tính bằng đô la) giữa EMA 34 và 89 của M15 để coi là xu hướng mạnh.
                - Nó cũng cần các tham số cho CombinedScalpingStrategy bên dưới.
        """
        super().__init__(params)
        self.m15_ema_strength_threshold = params.get('m15_ema_strength_threshold', 0.5)
        # Thêm các tham số cho bộ lọc mô hình nến
        self.bullish_candle_patterns = params.get('bullish_candle_patterns', ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR'])
        self.bearish_candle_patterns = params.get('bearish_candle_patterns', ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR'])
        self.min_candle_confirmations = params.get('min_candle_confirmations', 1) # Số lượng mô hình nến tối thiểu để xác nhận
        self.adx_length = params.get('adx_length', 14) # Độ dài ADX
        self.adx_trend_threshold = params.get('adx_trend_threshold', 25) # Suggestion: Only trade when ADX > 25
        self.adx_range_threshold = params.get('adx_range_threshold', 20) # Suggestion: Skip trades when ADX < 20
        self.bbw_threshold = params.get('bbw_threshold', 0.003) # Ngưỡng Bollinger Bandwidth để xác nhận thị trường đi ngang

        self.use_h1_trend_filter = params.get('use_h1_trend_filter', False)
        self.use_h4_trend_filter = params.get('use_h4_trend_filter', False)
        # Tham số cho SL/TP động mới
        self.use_dynamic_ema_sltp = params.get('use_dynamic_ema_sltp', False)
        self.dynamic_sltp_rr_ratio = params.get('dynamic_sltp_rr_ratio', 1.5)
        self.sl_buffer_points = params.get('sl_buffer_points', 0.2)
        # Khởi tạo các chiến lược con
        self.combined_scalping_strategy = CombinedScalpingStrategy(params)
        self.mean_reversion_strategy = BollingerBandMeanReversionStrategy(params.get('BollingerBandMeanReversionStrategy', {}))

    def _get_dynamic_ema_sltp(self, latest_data, signal):
        """Tính toán SL/TP dựa trên các đường EMA của M15, H1, H4."""
        # SỬA LỖI: Sử dụng giá M5 làm giá vào lệnh cho các chiến lược scalping
        # Cột 'CLOSE' không tồn tại trong `analyzed_data` đã được hợp nhất.
        entry_price = latest_data['CLOSE_M5']
        
        if signal == 1: # BUY
            # Tìm các mức hỗ trợ EMA bên dưới giá hiện tại
            supports = [
                latest_data.get('M15_EMA_34'), latest_data.get('M15_EMA_89'),
                latest_data.get('H1_EMA_34'), latest_data.get('H1_EMA_89'),
                latest_data.get('H4_EMA_34'), latest_data.get('H4_EMA_89')
            ]
            valid_supports = [s for s in supports if s is not None and s < entry_price]
            if not valid_supports: return None, None
            
            # SL được đặt dưới mức hỗ trợ thấp nhất (an toàn nhất)
            stop_loss = min(valid_supports) - self.sl_buffer_points
            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * self.dynamic_sltp_rr_ratio)
            return stop_loss, take_profit

        elif signal == -1: # SELL
            resistances = [
                latest_data.get('M15_EMA_34'), latest_data.get('M15_EMA_89'),
                latest_data.get('H1_EMA_34'), latest_data.get('H1_EMA_89'),
                latest_data.get('H4_EMA_34'), latest_data.get('H4_EMA_89')
            ]
            valid_resistances = [r for r in resistances if r is not None and r > entry_price]
            if not valid_resistances: return None, None

            stop_loss = max(valid_resistances) + self.sl_buffer_points
            sl_distance = stop_loss - entry_price
            take_profit = entry_price - (sl_distance * self.dynamic_sltp_rr_ratio)
            return stop_loss, take_profit

        return None, None

    def get_signal(self, analyzed_data):
        """
        Kiểm tra sức mạnh và sự đồng thuận của xu hướng M15, sau đó lấy tín hiệu từ chiến lược kết hợp.
        """
        latest = analyzed_data.iloc[-1]

        # --- 0. Bộ lọc Mô hình Nến (Candlestick Pattern Filter) ---
        # Đếm số lượng mô hình nến tăng/giảm giá được tìm thấy
        bullish_candle_votes = sum(1 for p in self.bullish_candle_patterns if latest.get(p, 0) > 0)
        bearish_candle_votes = sum(1 for p in self.bearish_candle_patterns if latest.get(p, 0) < 0)

        candle_signal = 0
        if bullish_candle_votes >= self.min_candle_confirmations:
            candle_signal = 1
        elif bearish_candle_votes >= self.min_candle_confirmations:
            candle_signal = -1

        if candle_signal == 0:
            # print("Candlestick filter: No sufficient candle pattern found. No signal.")
            return 0, None, None # Không có mô hình nến phù hợp, không có tín hiệu

        # --- 1. Phát hiện trạng thái thị trường bằng ADX M15 ---
        m15_adx = latest.get(f'ADX_{self.adx_length}_M15')
        if m15_adx is None:
            return 0, None, None

        scalping_signal, sl, tp = 0, None, None
        strategy_used_name = "None"

        if m15_adx >= self.adx_trend_threshold:
            # Thị trường có xu hướng mạnh, sử dụng chiến lược Trend-Following
            strategy_used_name = "Trend"
            
            # Áp dụng các bộ lọc của M15FilteredScalpingStrategy cho chiến lược xu hướng
            # Bộ lọc 1: Sức mạnh xu hướng (khoảng cách tuyệt đối giữa các đường EMA)
            m15_ema_34 = latest.get('M15_EMA_34')
            m15_ema_89 = latest.get('M15_EMA_89')
            if m15_ema_34 is None or m15_ema_89 is None:
                return 0, None, None
            ema_distance = abs(m15_ema_34 - m15_ema_89)
            if ema_distance < self.m15_ema_strength_threshold:
                return 0, None, None # Xu hướng không đủ mạnh

            # Bộ lọc 2: Đồng thuận xu hướng M15 (EMA ngắn, trung)
            is_m15_uptrend = (m15_ema_34 > m15_ema_89)
            is_m15_downtrend = (m15_ema_34 < m15_ema_89)

            # Lấy tín hiệu từ CombinedScalpingStrategy
            temp_signal, temp_sl, temp_tp = self.combined_scalping_strategy.get_signal(analyzed_data)
            
            # Đảm bảo tín hiệu phù hợp với xu hướng M15
            if (temp_signal == 1 and is_m15_uptrend) or \
               (temp_signal == -1 and is_m15_downtrend):
                scalping_signal, sl, tp = temp_signal, temp_sl, temp_tp

            # Bộ lọc 3 & 4: Đồng thuận xu hướng H1/H4 (nếu được bật)
            if scalping_signal != 0 and self.use_h1_trend_filter:
                h1_trend = latest.get('H1_TREND', 0)
                if (scalping_signal == 1 and h1_trend != 1) or \
                   (scalping_signal == -1 and h1_trend != -1):
                    scalping_signal = 0 # Vô hiệu hóa tín hiệu
            if scalping_signal != 0 and self.use_h4_trend_filter:
                h4_trend = latest.get('H4_TREND', 0)
                if (scalping_signal == 1 and h4_trend != 1) or \
                   (scalping_signal == -1 and h4_trend != -1):
                    scalping_signal = 0 # Vô hiệu hóa tín hiệu

        elif m15_adx <= self.adx_range_threshold:
            # Thị trường không có xu hướng, kiểm tra thêm điều kiện co thắt (squeeze)
            bb_length = self.mean_reversion_strategy.bb_length
            bb_std_dev = self.mean_reversion_strategy.bb_std_dev
            bbw_col_name = f'BBW_{bb_length}_{bb_std_dev}.0'
            m5_bbw = latest.get(bbw_col_name)

            # Chỉ kích hoạt chiến lược Range nếu thị trường đang co thắt (biến động thấp)
            if m5_bbw is not None and m5_bbw < self.bbw_threshold:
                strategy_used_name = "Range"
                scalping_signal, sl, tp = self.mean_reversion_strategy.get_signal(analyzed_data)
                # Không áp dụng các bộ lọc xu hướng M15, H1, H4 cho chiến lược này
                # vì nó được thiết kế cho thị trường đi ngang.

        
        # Nếu không có tín hiệu từ cả hai chiến lược, hoặc ADX nằm giữa các ngưỡng, thì không giao dịch
        if scalping_signal == 0:
            return 0, None, None

        # --- 2. Đảm bảo tín hiệu scalping khớp với tín hiệu nến ---
        if scalping_signal != candle_signal:
            return 0, None, None
            
        # --- 3. Logic SL/TP Động Mới ---
        # (Áp dụng cho cả hai chiến lược nếu use_dynamic_ema_sltp là True)
        m15_ema_34 = latest.get('M15_EMA_34')
        m15_ema_89 = latest.get('M15_EMA_89')
        if self.use_dynamic_ema_sltp:
            dynamic_sl, dynamic_tp = self._get_dynamic_ema_sltp(latest, scalping_signal)
            if dynamic_sl is not None and dynamic_tp is not None:
                print(f"Tín hiệu {strategy_used_name} được M15 Filter xác nhận: {scalping_signal} với SL/TP động")
                return scalping_signal, dynamic_sl, dynamic_tp
            # Nếu không tìm được SL/TP động hợp lệ, bỏ qua tín hiệu để an toàn
            return 0, None, None

        # Nếu tất cả các bộ lọc đều qua, trả về tín hiệu ban đầu
        print(f"Tín hiệu {strategy_used_name} được M15 Filter xác nhận: {scalping_signal}")
        return scalping_signal, sl, tp