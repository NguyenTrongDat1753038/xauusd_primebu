# -*- coding: utf-8 -*-
"""
Pattern Recognition Utilities cho EURGBP Swing Strategy
Cung cấp các hàm nhận dạng pattern với tiêu chí rõ ràng và có thể cấu hình
"""

import pandas as pd
import numpy as np

class EURGBPPatterns:
    """
    Class chứa các hàm nhận dạng pattern cho EURGBP với tiêu chí rõ ràng
    """

    def __init__(self, params=None):
        self.params = params or {}

        # Pin Bar parameters
        self.pin_bar_body_ratio = self.params.get('pin_bar_body_ratio', 0.3)  # Body < 30% của total range
        self.pin_bar_wick_ratio = self.params.get('pin_bar_wick_ratio', 2.0)  # Wick > 2x body

        # Engulfing parameters
        self.engulfing_body_multiplier = self.params.get('engulfing_body_multiplier', 1.5)  # Body > 1.5x body của nến trước
        self.engulfing_min_body_ratio = self.params.get('engulfing_min_body_ratio', 0.6)  # Body > 60% của total range

        # Fakey parameters
        self.fakey_wick_penetration = self.params.get('fakey_wick_penetration', 0.7)  # Wick phải đâm qua 70% body của nến mẹ
        self.fakey_confirmation_bars = self.params.get('fakey_confirmation_bars', 1)  # Số nến xác nhận

    def is_pin_bar(self, candle, is_bearish=True):
        """
        Nhận dạng Pin Bar với tiêu chí rõ ràng

        Args:
            candle: Series chứa OHLC
            is_bearish: True cho bearish pin bar, False cho bullish pin bar

        Returns:
            bool: True nếu là pin bar hợp lệ
        """
        try:
            high = candle['high']
            low = candle['low']
            open_price = candle['open']
            close = candle['close']

            total_range = high - low
            if total_range <= 0:
                return False

            body = abs(close - open_price)
            body_ratio = body / total_range

            # Body phải nhỏ (< 30% total range)
            if body_ratio >= self.pin_bar_body_ratio:
                return False

            if is_bearish:
                # Bearish Pin Bar: upper wick phải > 2x body
                upper_wick = high - max(open_price, close)
                lower_wick = min(open_price, close) - low

                wick_ratio = upper_wick / body if body > 0 else float('inf')
                return wick_ratio >= self.pin_bar_wick_ratio and upper_wick > lower_wick
            else:
                # Bullish Pin Bar: lower wick phải > 2x body
                upper_wick = high - max(open_price, close)
                lower_wick = min(open_price, close) - low

                wick_ratio = lower_wick / body if body > 0 else float('inf')
                return wick_ratio >= self.pin_bar_wick_ratio and lower_wick > upper_wick

        except (KeyError, ZeroDivisionError):
            return False

    def is_engulfing(self, current_candle, prev_candle, is_bearish=True):
        """
        Nhận dạng Engulfing Pattern với tiêu chí rõ ràng

        Args:
            current_candle: Nến hiện tại
            prev_candle: Nến trước đó
            is_bearish: True cho bearish engulfing, False cho bullish engulfing

        Returns:
            bool: True nếu là engulfing hợp lệ
        """
        try:
            curr_high = current_candle['high']
            curr_low = current_candle['low']
            curr_open = current_candle['open']
            curr_close = current_candle['close']

            prev_high = prev_candle['high']
            prev_low = prev_candle['low']
            prev_open = prev_candle['open']
            prev_close = prev_candle['close']

            curr_body = abs(curr_close - curr_open)
            prev_body = abs(prev_close - prev_open)

            curr_total_range = curr_high - curr_low
            prev_total_range = prev_high - prev_low

            if curr_total_range <= 0 or prev_total_range <= 0:
                return False

            # Body hiện tại phải > 1.5x body trước đó
            if curr_body < self.engulfing_body_multiplier * prev_body:
                return False

            # Body phải > 60% total range
            if curr_body / curr_total_range < self.engulfing_min_body_ratio:
                return False

            if is_bearish:
                # Bearish Engulfing: phải bao phủ hoàn toàn nến tăng trước đó
                return (curr_open > prev_close and curr_close < prev_open and
                       curr_high >= prev_high and curr_low <= prev_low)
            else:
                # Bullish Engulfing: phải bao phủ hoàn toàn nến giảm trước đó
                return (curr_open < prev_close and curr_close > prev_open and
                       curr_high >= prev_high and curr_low <= prev_low)

        except (KeyError, ZeroDivisionError):
            return False

    def is_fakey(self, candles_df, current_idx, is_bearish=True):
        """
        Nhận dạng Fakey Pattern với tiêu chí rõ ràng

        Args:
            candles_df: DataFrame chứa nhiều nến
            current_idx: Index của nến mẹ (inside bar)
            is_bearish: True cho bearish fakey, False cho bullish fakey

        Returns:
            bool: True nếu là fakey hợp lệ
        """
        try:
            if current_idx < 1 or current_idx >= len(candles_df) - self.fakey_confirmation_bars:
                return False

            # Nến mẹ (inside bar)
            mother_candle = candles_df.iloc[current_idx]
            mother_high = mother_candle['high']
            mother_low = mother_candle['low']
            mother_body_high = max(mother_candle['open'], mother_candle['close'])
            mother_body_low = min(mother_candle['open'], mother_candle['close'])

            # Nến trước đó (breakout bar)
            prev_candle = candles_df.iloc[current_idx - 1]
            prev_high = prev_candle['high']
            prev_low = prev_candle['low']

            # Kiểm tra inside bar: nến mẹ nằm trong range của nến trước
            if not (mother_high <= prev_high and mother_low >= prev_low):
                return False

            # Nến xác nhận (confirmation bar)
            conf_candle = candles_df.iloc[current_idx + 1]
            conf_open = conf_candle['open']
            conf_close = conf_candle['close']
            conf_high = conf_candle['high']
            conf_low = conf_candle['low']

            if is_bearish:
                # Bearish Fakey: wick phải đâm qua body của mother candle từ trên xuống
                wick_penetration = (mother_body_high - conf_low) / (mother_body_high - mother_body_low)
                fake_breakout = conf_high > mother_high  # Phá vỡ lên trên

                # Xác nhận giảm giá
                confirmation = conf_close < mother_body_high

                return (fake_breakout and wick_penetration >= self.fakey_wick_penetration and confirmation)
            else:
                # Bullish Fakey: wick phải đâm qua body của mother candle từ dưới lên
                wick_penetration = (conf_high - mother_body_low) / (mother_body_high - mother_body_low)
                fake_breakout = conf_low < mother_low  # Phá vỡ xuống dưới

                # Xác nhận tăng giá
                confirmation = conf_close > mother_body_low

                return (fake_breakout and wick_penetration >= self.fakey_wick_penetration and confirmation)

        except (KeyError, ZeroDivisionError, IndexError):
            return False

    def detect_patterns(self, candles_df, current_idx=None):
        """
        Phát hiện tất cả pattern có thể có tại nến hiện tại

        Args:
            candles_df: DataFrame chứa OHLCV
            current_idx: Index của nến cần kiểm tra (mặc định là nến cuối)

        Returns:
            dict: Dictionary chứa các pattern được phát hiện
        """
        if current_idx is None:
            current_idx = len(candles_df) - 1

        if current_idx < 1 or current_idx >= len(candles_df):
            return {}

        current_candle = candles_df.iloc[current_idx]
        prev_candle = candles_df.iloc[current_idx - 1]

        patterns = {
            'pin_bar_bullish': self.is_pin_bar(current_candle, is_bearish=False),
            'pin_bar_bearish': self.is_pin_bar(current_candle, is_bearish=True),
            'engulfing_bullish': self.is_engulfing(current_candle, prev_candle, is_bearish=False),
            'engulfing_bearish': self.is_engulfing(current_candle, prev_candle, is_bearish=True),
            'fakey_bullish': self.is_fakey(candles_df, current_idx, is_bearish=False),
            'fakey_bearish': self.is_fakey(candles_df, current_idx, is_bearish=True)
        }

        return patterns

def find_key_levels(candles_df, lookback_period=50):
    """
    Tìm các level quan trọng (support/resistance) từ dữ liệu lịch sử

    Args:
        candles_df: DataFrame OHLCV
        lookback_period: Số nến để tìm level

    Returns:
        dict: Dictionary chứa support và resistance levels
    """
    if len(candles_df) < lookback_period:
        return {'support': [], 'resistance': []}

    recent_data = candles_df.tail(lookback_period)

    # Tìm swing highs và swing lows
    highs = recent_data['high'].values
    lows = recent_data['low'].values

    swing_highs = []
    swing_lows = []

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            swing_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            swing_lows.append(lows[i])

    # Lấy các level mạnh nhất (được test nhiều lần)
    resistance_levels = sorted(list(set(swing_highs)), reverse=True)[:3] if swing_highs else []
    support_levels = sorted(list(set(swing_lows)))[:3] if swing_lows else []

    return {
        'support': support_levels,
        'resistance': resistance_levels
    }

def calculate_smart_sl(entry_price, atr_value, key_levels, is_buy=True, atr_multiplier=1.5):
    """
    Tính SL thông minh: min của ATR-based SL và distance đến key level gần nhất

    Args:
        entry_price: Giá vào lệnh
        atr_value: Giá trị ATR
        key_levels: Dictionary chứa support/resistance
        is_buy: True cho lệnh BUY, False cho SELL
        atr_multiplier: Hệ số nhân với ATR

    Returns:
        float: SL price được tính toán
    """
    # SL dựa trên ATR
    atr_sl_distance = atr_value * atr_multiplier

    if is_buy:
        atr_sl = entry_price - atr_sl_distance
        # Tìm resistance level gần nhất phía trên entry
        nearby_resistances = [level for level in key_levels.get('resistance', []) if level > entry_price]
        if nearby_resistances:
            structure_sl = min(nearby_resistances) - 0.0001  # Cách 1 pip
            final_sl = max(atr_sl, structure_sl)  # Chọn SL xa hơn (an toàn hơn)
        else:
            final_sl = atr_sl
    else:
        atr_sl = entry_price + atr_sl_distance
        # Tìm support level gần nhất phía dưới entry
        nearby_supports = [level for level in key_levels.get('support', []) if level < entry_price]
        if nearby_supports:
            structure_sl = max(nearby_supports) + 0.0001  # Cách 1 pip
            final_sl = min(atr_sl, structure_sl)  # Chọn SL xa hơn (an toàn hơn)
        else:
            final_sl = atr_sl

    return final_sl