from .base_strategy import BaseStrategy
import pandas as pd
import numpy as np

class MTF_EMA_M1_Trigger_Strategy(BaseStrategy):
    """
    Chiến lược này kết hợp bộ lọc xu hướng đa khung thời gian (tương tự MultiTimeframeEmaStrategy)
    với một bộ kích hoạt tín hiệu trên khung M1.

    - Bộ lọc xu hướng: Sử dụng sự đồng thuận của xu hướng trên H1 và M30.
    - Bộ lọc bối cảnh: Giá phải nằm trên/dưới các đường EMA chính của M15 (EMA 34, 89).
    - Bộ kích hoạt vào lệnh (Trigger): Một cây nến M1 có thân nến lớn bất thường,
      cho thấy một cú giật giá mạnh theo hướng của xu hướng chính.
    """
    def __init__(self, params):
        """
        Khởi tạo chiến lược.

        Args:
            params (dict): Từ điển chứa các tham số.
                - 'm1_body_size_threshold' (float): Ngưỡng kích thước thân nến M1
                  (ví dụ: 0.5 đô la) để được coi là một cú giật giá.
                - 'm15_ema_separation_threshold' (float): Khoảng cách tối thiểu giữa giá đóng cửa M1
                  và EMA 89 của M15 để đảm bảo giá không quá xa xu hướng.
        """
        super().__init__(params)
        self.m1_body_size_threshold = params.get('m1_body_size_threshold', 0.5)
        self.m15_ema_separation_threshold = params.get('m15_ema_separation_threshold', 5.0) # Dùng cho M15 context
        # Ngưỡng cho phép giá nằm gần H1 EMA 89 (kháng cự động) khi xu hướng giảm
        self.h1_resistance_tolerance = params.get('h1_resistance_tolerance', 1.0) 

    def get_signal(self, analyzed_data: pd.DataFrame):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        close_price = latest['CLOSE']

        # --- 1. Bộ lọc xu hướng đa khung thời gian (HTF) ---
        h1_trend = latest.get('H1_TREND', 0)
        m30_trend = latest.get('M30_TREND', 0)

        is_uptrend_aligned = (h1_trend == 1) and (m30_trend == 1)
        is_downtrend_aligned = (h1_trend == -1) and (m30_trend == -1)

        # --- 2. Bộ lọc bối cảnh M15 ---
        m15_ema_34 = latest.get('M15_EMA_34')
        m15_ema_89 = latest.get('M15_EMA_89')
        if pd.isna(m15_ema_34) or pd.isna(m15_ema_89):
            return 0, None, None

        # Context M15 truyền thống
        is_m15_context_bullish_traditional = close_price > m15_ema_34 > m15_ema_89 and abs(close_price - m15_ema_89) < self.m15_ema_separation_threshold
        is_m15_context_bearish_traditional = close_price < m15_ema_34 < m15_ema_89 and abs(close_price - m15_ema_89) < self.m15_ema_separation_threshold

        # Context M15 linh hoạt hơn cho tín hiệu bán khi giá chạm kháng cự H1
        h1_ema_89 = latest.get('H1_EMA_89')
        is_m15_context_bearish_flexible = False
        if not pd.isna(h1_ema_89):
            # Giá nằm gần H1 EMA 89 (kháng cự động) và nằm dưới nó một chút
            is_m15_context_bearish_flexible = (close_price <= h1_ema_89 + self.h1_resistance_tolerance) and (close_price >= h1_ema_89 - self.h1_resistance_tolerance)

        # --- 3. Bộ kích hoạt (Trigger) trên M1 ---
        m1_body_size = abs(latest['CLOSE'] - latest['OPEN'])
        is_strong_bullish_m1 = latest['CLOSE'] > latest['OPEN'] and m1_body_size > self.m1_body_size_threshold
        is_strong_bearish_m1 = latest['CLOSE'] < latest['OPEN'] and m1_body_size > self.m1_body_size_threshold

        # --- 4. Tạo tín hiệu ---
        if is_uptrend_aligned and is_m15_context_bullish_traditional and is_strong_bullish_m1:
            print(f"Tín hiệu MUA (M1 Trigger): HTF Up, M15 Context Bullish, M1 Spike (Body: {m1_body_size:.2f})")
            return 1, None, None

        if is_downtrend_aligned and (is_m15_context_bearish_traditional or is_m15_context_bearish_flexible) and is_strong_bearish_m1:
            print(f"Tín hiệu BÁN (M1 Trigger): HTF Down, M15 Context Bearish, M1 Spike (Body: {m1_body_size:.2f})")
            return -1, None, None

        return 0, None, None