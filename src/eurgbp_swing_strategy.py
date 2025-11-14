# -*- coding: utf-8 -*-
from .base_strategy import BaseStrategy
import pandas as pd
from .eurgbp_patterns import EURGBPPatterns, find_key_levels, calculate_smart_sl
import datetime

class EurgbpSwingStrategy(BaseStrategy):
    """
    Chiến lược Swing Trade cho EURGBP dựa trên xu hướng đa khung thời gian (D1, H4, H1).
    - Xu hướng chính: EMA(34, 89) trên D1.
    - Cấu trúc và bộ lọc: EMA(34, 89) trên H4.
    - Tín hiệu vào lệnh: EMA(34, 89), mô hình nến, và ATR trên H1.
    """
    def __init__(self, params):
        super().__init__(params)
        # Lấy các tham số từ config
        self.ema_fast_len = params.get('ema_fast', 34)
        self.ema_slow_len = params.get('ema_slow', 89)
        self.atr_period = params.get('atr_period', 14)
        self.atr_mult_sl = params.get('atr_mult_sl', 1.5)
        self.atr_mult_tp = params.get('atr_mult_tp', 2.5)
        self.min_h1_atr = params.get('min_h1_atr', 0.0005)
        self.d1_sideways_threshold = params.get('d1_sideways_threshold', 0.0100) # 100 pips

        # Pattern recognition parameters
        pattern_params = params.get('patterns', {})
        self.pattern_recognizer = EURGBPPatterns(pattern_params)

        # News/Event filter parameters
        news_params = params.get('news_filter', {})
        self.news_filter_enabled = news_params.get('enabled', True)
        self.news_avoid_hours_before = news_params.get('avoid_hours_before', 2)
        self.news_avoid_hours_after = news_params.get('avoid_hours_after', 2)

        # Key events for EURGBP (BOE/ECB events)
        self.key_events = news_params.get('events', [
            'BOE_Rate_Decision', 'ECB_Rate_Decision', 'BOE_MPC_Meeting',
            'ECB_Press_Conference', 'UK_CPI', 'EU_CPI', 'UK_GDP', 'EU_GDP',
            'UK_PMI', 'EU_PMI', 'UK_Unemployment', 'EU_Unemployment'
        ])

        # Exit logic parameters
        exit_params = params.get('exit_logic', {})
        self.partial_close_at_tp1 = exit_params.get('partial_close_at_tp1', True)
        self.partial_close_percent = exit_params.get('partial_close_percent', 0.5)
        self.trailing_ema_period = exit_params.get('trailing_ema_period', 34)
        self.trailing_ema_timeframe = exit_params.get('trailing_ema_timeframe', 'h1')

        # Định nghĩa các mô hình nến (backup nếu pattern recognition fail)
        self.bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        self.bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']

    def is_news_event_time(self, current_time=None):
        """
        Kiểm tra xem thời điểm hiện tại có nằm trong khoảng tránh news/event không

        Args:
            current_time: datetime object, mặc định là thời gian hiện tại

        Returns:
            bool: True nếu nên tránh trade do news/event
        """
        if not self.news_filter_enabled:
            return False

        if current_time is None:
            current_time = datetime.datetime.now(datetime.timezone.utc)

        # Chuyển về giờ London (GMT/BST)
        london_time = current_time

        # Kiểm tra các event quan trọng
        # Đây là logic đơn giản - trong thực tế nên tích hợp với economic calendar API
        weekday = london_time.weekday()  # 0=Monday, 4=Friday
        hour = london_time.hour
        minute = london_time.minute

        # BOE MPC Meeting: Thứ Năm hàng tuần, thường 12:00 GMT
        if weekday == 3 and 11 <= hour <= 13:  # Thứ Năm 11:00-13:00
            return True

        # ECB Press Conference: Thứ Năm, thường 14:45 CET (13:45 GMT)
        if weekday == 3 and 13 <= hour <= 15:  # Thứ Năm 13:00-15:00
            return True

        # Economic data releases - High impact
        # UK CPI: thường 7:00 GMT vào ngày 19 hàng tháng
        # EU CPI: thường 10:00 CET (9:00 GMT)
        # UK GDP: thường 7:00 GMT vào ngày 31 hàng tháng
        # EU GDP: thường 10:00 CET (9:00 GMT)

        # Simplified check: tránh trade vào buổi sáng các ngày đầu tháng
        if london_time.day <= 5:  # Ngày 1-5 hàng tháng
            if 6 <= hour <= 11:  # 6:00-11:00 GMT
                return True

        # Tránh trade vào các ngày lễ quan trọng
        # Christmas, New Year, Easter, etc.
        month = london_time.month
        day = london_time.day

        # Christmas period
        if month == 12 and 20 <= day <= 31:
            return True
        if month == 1 and day <= 3:
            return True

        # Easter (approximate)
        if month == 4 and 10 <= day <= 20:
            return True

        return False

    def get_signal(self, analyzed_data):
        """
        Xác định tín hiệu BUY hoặc SELL dựa trên các điều kiện của chiến lược.
        """
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2]

        # --- 1. Kiểm tra News/Event Filter ---
        if self.is_news_event_time():
            print("⚠️  Tránh trade do thời gian News/Event quan trọng.")
            return 0, None, None

        # --- 2. Kiểm tra các điều kiện lọc cơ bản ---
        # Lấy các giá trị cần thiết từ DataFrame
        d1_ema_fast = latest.get(f'D1_EMA_{self.ema_fast_len}')
        d1_ema_slow = latest.get(f'D1_EMA_{self.ema_slow_len}')
        h1_atr = latest.get(f'H1_ATR_{self.atr_period}')

        if pd.isna(d1_ema_fast) or pd.isna(d1_ema_slow) or pd.isna(h1_atr):
            print("Cảnh báo: Thiếu dữ liệu EMA D1 hoặc ATR H1 để phân tích.")
            return 0, None, None

        # Lọc 1: Thị trường Daily đi ngang
        if abs(d1_ema_fast - d1_ema_slow) < self.d1_sideways_threshold:
            print(f"Thị trường Daily đi ngang (EMA distance < {self.d1_sideways_threshold}). Bỏ qua.")
            return 0, None, None

        # Lọc 2: Biến động H1 quá thấp
        if h1_atr < self.min_h1_atr:
            print(f"Biến động H1 quá thấp (ATR < {self.min_h1_atr}). Bỏ qua.")
            return 0, None, None

        # --- 3. Xác định xu hướng đa khung thời gian ---
        d1_trend_is_up = d1_ema_fast > d1_ema_slow
        h4_ema_fast = latest.get(f'H4_EMA_{self.ema_fast_len}')
        h4_ema_slow = latest.get(f'H4_EMA_{self.ema_slow_len}')
        h4_trend_is_up = h4_ema_fast > h4_ema_slow if not (pd.isna(h4_ema_fast) or pd.isna(h4_ema_slow)) else d1_trend_is_up

        # --- 4. Phát hiện pattern với tiêu chí rõ ràng ---
        h1_candles = analyzed_data[['H1_OPEN', 'H1_HIGH', 'H1_LOW', 'H1_CLOSE']].rename(
            columns={'H1_OPEN': 'open', 'H1_HIGH': 'high', 'H1_LOW': 'low', 'H1_CLOSE': 'close'}
        )

        patterns = self.pattern_recognizer.detect_patterns(h1_candles)

        # Backup: sử dụng TA-Lib patterns nếu pattern recognition mới fail
        is_bullish_candle = any(latest.get(p, 0) > 0 for p in self.bullish_patterns) or patterns.get('pin_bar_bullish', False) or patterns.get('engulfing_bullish', False) or patterns.get('fakey_bullish', False)
        is_bearish_candle = any(latest.get(p, 0) < 0 for p in self.bearish_patterns) or patterns.get('pin_bar_bearish', False) or patterns.get('engulfing_bearish', False) or patterns.get('fakey_bearish', False)

        # --- 5. Tìm tín hiệu vào lệnh trên H1 ---
        h1_close = latest.get('H1_CLOSE')
        h1_ema_fast = latest.get(f'H1_EMA_{self.ema_fast_len}')
        h1_ema_slow = latest.get(f'H1_EMA_{self.ema_slow_len}')

        h1_ema_fast_prev = previous.get(f'H1_EMA_{self.ema_fast_len}')
        h1_ema_slow_prev = previous.get(f'H1_EMA_{self.ema_slow_len}')

        if any(pd.isna(v) for v in [h1_close, h1_ema_fast, h1_ema_slow, h1_ema_fast_prev, h1_ema_slow_prev]):
            print("Cảnh báo: Thiếu dữ liệu EMA H1 để tìm tín hiệu.")
            return 0, None, None

        # Điều kiện giao cắt EMA trên H1
        h1_bullish_cross = h1_ema_fast_prev < h1_ema_slow_prev and h1_ema_fast > h1_ema_slow
        h1_bearish_cross = h1_ema_fast_prev > h1_ema_slow_prev and h1_ema_fast < h1_ema_slow

        # Điều kiện giá hồi về vùng EMA
        price_pulled_back_to_ema_buy = (latest.get('H1_LOW') < h1_ema_slow) and (h1_close > h1_ema_fast)
        price_pulled_back_to_ema_sell = (latest.get('H1_HIGH') > h1_ema_slow) and (h1_close < h1_ema_fast)

        signal = 0

        # --- Điều kiện vào lệnh BUY ---
        if d1_trend_is_up and h4_trend_is_up:
            # Tín hiệu 1: Pattern xác nhận tăng giá tại vùng EMA
            if is_bullish_candle and price_pulled_back_to_ema_buy:
                pattern_names = [k for k, v in patterns.items() if v and 'bullish' in k]
                pattern_str = ', '.join(pattern_names) if pattern_names else 'TA-Lib pattern'
                print(f"📈 Tín hiệu BUY: {pattern_str} tại vùng EMA H1.")
                signal = 1
            # Tín hiệu 2: EMA H1 cắt lên
            elif h1_bullish_cross:
                print("📈 Tín hiệu BUY: EMA H1 cắt lên.")
                signal = 1

        # --- Điều kiện vào lệnh SELL ---
        elif not d1_trend_is_up and not h4_trend_is_up:
            # Tín hiệu 1: Pattern xác nhận giảm giá tại vùng EMA
            if is_bearish_candle and price_pulled_back_to_ema_sell:
                pattern_names = [k for k, v in patterns.items() if v and 'bearish' in k]
                pattern_str = ', '.join(pattern_names) if pattern_names else 'TA-Lib pattern'
                print(f"📉 Tín hiệu SELL: {pattern_str} tại vùng EMA H1.")
                signal = -1
            # Tín hiệu 2: EMA H1 cắt xuống
            elif h1_bearish_cross:
                print("📉 Tín hiệu SELL: EMA H1 cắt xuống.")
                signal = -1

        # --- 6. Tính toán SL/TP thông minh nếu có tín hiệu ---
        if signal != 0:
            entry_price = h1_close

            # Tìm key levels từ H1 data
            h1_data_for_levels = analyzed_data[['H1_HIGH', 'H1_LOW']].rename(
                columns={'H1_HIGH': 'high', 'H1_LOW': 'low'}
            )
            key_levels = find_key_levels(h1_data_for_levels, lookback_period=50)

            # Tính SL thông minh
            stop_loss = calculate_smart_sl(
                entry_price=entry_price,
                atr_value=h1_atr,
                key_levels=key_levels,
                is_buy=(signal == 1),
                atr_multiplier=self.atr_mult_sl
            )

            # Tính TP dựa trên ATR
            tp_distance = h1_atr * self.atr_mult_tp
            if signal == 1: # BUY
                take_profit = entry_price + tp_distance
            else: # SELL
                take_profit = entry_price - tp_distance

            # Kiểm tra R:R tối thiểu
            sl_distance = abs(entry_price - stop_loss)
            rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

            if rr_ratio < 1.5:
                print(f"⚠️  R:R ratio quá thấp ({rr_ratio:.2f} < 1.5). Bỏ qua tín hiệu.")
                return 0, None, None

            print(f"✅ Tín hiệu được xác nhận: {'BUY' if signal == 1 else 'SELL'}")
            print(f"Entry: {entry_price:.5f}, SL: {stop_loss:.5f}, TP: {take_profit:.5f}")
            print(f"ATR: {h1_atr:.5f}, R:R: {rr_ratio:.2f}, Key Levels: S:{key_levels['support'][:2]}, R:{key_levels['resistance'][:2]}")
            return signal, stop_loss, take_profit

        return 0, None, None