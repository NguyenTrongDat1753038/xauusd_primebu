from .base_strategy import BaseStrategy
from .combined_strategy import CombinedScalpingStrategy
from .bollinger_band_mean_reversion_strategy import BollingerBandMeanReversionStrategy
import pandas as pd
from datetime import datetime, time
import logging

class M15FilteredScalpingStrategy(BaseStrategy):
    """
    Chiến lược scalping nâng cao với bộ lọc M15 và nhiều cải tiến:
    - Tự động chuyển đổi giữa scalping theo xu hướng và đảo chiều
    - Bộ lọc RSI để tránh tín hiệu giả
    - Bộ lọc khối lượng xác nhận
    - Ngưỡng trễ chuyển đổi chế độ
    - Quản lý rủi ro động theo ATR
    - Xác nhận đa khung thời gian
    - Bộ lọc thời gian giao dịch
    """

    def __init__(self, params):
        super().__init__(params)
        
        # Tham số ADX cơ bản
        self.adx_length = params.get('adx_length', 14)
        self.adx_trend_threshold = params.get('adx_trend_threshold', 25)
        self.adx_range_threshold = params.get('adx_range_threshold', 20)
        self.adx_hysteresis = params.get('adx_hysteresis', 2)  # Ngưỡng trễ
        
        # Bộ lọc RSI
        self.use_rsi_filter = params.get('use_rsi_filter', True)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        
        # Bộ lọc khối lượng
        self.use_volume_filter = params.get('use_volume_filter', True)
        self.min_volume_ratio = params.get('min_volume_ratio', 0.8)
        
        # Xác nhận đa khung thời gian
        self.use_trend_confirmation = params.get('use_trend_confirmation', True)
        self.min_trend_score = params.get('min_trend_score', 2)  # 2/3 khung cùng hướng
        
        # Quản lý rủi ro động
        self.use_dynamic_sltp = params.get('use_dynamic_sltp', True)
        self.atr_adjustment_threshold = params.get('atr_adjustment_threshold', 1.5)
        
        # Bộ lọc thời gian
        self.use_time_filter = params.get('use_time_filter', False)
        self.trading_hours = params.get('trading_hours', {
            'start': '00:00',
            'end': '23:59'
        })
        
        # Khởi tạo chiến lược con
        self.trend_strategy = CombinedScalpingStrategy(params.get('CombinedScalpingStrategy', {}))
        self.range_strategy = BollingerBandMeanReversionStrategy(params.get('BollingerBandMeanReversionStrategy', {}))
        
        # Biến trạng thái
        self.last_mode = None
        self.logger = logging.getLogger(__name__)

    def get_signal(self, analyzed_data):
        """
        Tạo tín hiệu giao dịch với nhiều bộ lọc nâng cao
        """
        # Kiểm tra dữ liệu đầu vào
        if len(analyzed_data) < 2 or analyzed_data.empty:
            return 0, None, None

        latest = analyzed_data.iloc[-1]

        # --- BỘ LỌC THỜI GIAN GIAO DỊCH ---
        if self.use_time_filter and not self._is_good_trading_time():
            self.logger.debug("Ngoài giờ giao dịch cho phép")
            return 0, None, None

        # --- BỘ LỌC KHỐI LƯỢNG ---
        if self.use_volume_filter and not self._check_volume_filter(analyzed_data, latest):
            self.logger.debug("Khối lượng không đủ")
            return 0, None, None

        # --- XÁC ĐỊNH CHẾ ĐỘ THỊ TRƯỜNG ---
        m15_adx = latest.get(f'ADX_{self.adx_length}_M15')
        if m15_adx is None or pd.isna(m15_adx):
            self.logger.warning("Không tìm thấy giá trị ADX M15")
            return 0, None, None

        current_mode = self._determine_market_mode(m15_adx)
        
        if current_mode == "None":
            self.logger.debug(f"Thị trường không rõ ràng (ADX M15 = {m15_adx:.2f})")
            return 0, None, None

        # --- LẤY TÍN HIỆU TỪ CHIẾN LƯỢC CON ---
        signal, sl, tp = 0, None, None
        strategy_used_name = "None"

        if current_mode == "Trend-Following":
            strategy_used_name = "Trend-Following"
            signal, sl, tp = self._get_trend_following_signal(analyzed_data, latest)
            
        elif current_mode == "Mean-Reversion":
            strategy_used_name = "Mean-Reversion"
            signal, sl, tp = self._get_mean_reversion_signal(analyzed_data, latest)

        # --- ÁP DỤNG CÁC BỘ LỌC BỔ SUNG ---
        if signal != 0:
            # Bộ lọc RSI
            if self.use_rsi_filter:
                original_signal = signal
                signal = self._apply_rsi_filter(signal, latest)
                if signal == 0 and original_signal != 0:
                    self.logger.debug(f"Tín hiệu bị hủy bởi bộ lọc RSI")

            # Xác nhận đa khung thời gian
            if self.use_trend_confirmation and signal != 0:
                original_signal = signal
                signal = self._apply_trend_confirmation(signal, latest)
                if signal == 0 and original_signal != 0:
                    self.logger.debug(f"Tín hiệu bị hủy do không đồng bộ xu hướng")

            # Điều chỉnh SL/TP động
            if signal != 0 and self.use_dynamic_sltp and sl is not None and tp is not None:
                sl, tp = self._adjust_sltp_dynamic(sl, tp, analyzed_data, latest)

        # --- GHI NHẬN KẾT QUẢ ---
        if signal != 0:
            self.logger.info(f"Tín hiệu {strategy_used_name}: {'BUY' if signal == 1 else 'SELL'}")
            if sl is not None and tp is not None:
                self.logger.info(f"SL: {sl:.5f}, TP: {tp:.5f}, R:R: {abs(tp - latest['CLOSE'])/abs(sl - latest['CLOSE']):.2f}")
            return signal, sl, tp

        return 0, None, None

    def _determine_market_mode(self, current_adx):
        """Xác định chế độ thị trường với ngưỡng trễ"""
        # Chuyển sang chế độ xu hướng khi ADX vượt ngưỡng + trễ
        if current_adx >= (self.adx_trend_threshold + self.adx_hysteresis):
            new_mode = "Trend-Following"
        # Chuyển sang chế độ đi ngang khi ADX dưới ngưỡng - trễ
        elif current_adx <= (self.adx_range_threshold - self.adx_hysteresis):
            new_mode = "Mean-Reversion"
        # Giữ nguyên chế độ cũ nếu trong vùng trễ
        elif self.last_mode and (self.adx_range_threshold < current_adx < self.adx_trend_threshold):
            new_mode = self.last_mode
        else:
            new_mode = "None"
        
        # Ghi nhận thay đổi chế độ
        if new_mode != self.last_mode and new_mode != "None":
            self.logger.info(f"Chuyển chế độ: {self.last_mode} -> {new_mode} (ADX: {current_adx:.2f})")
        
        self.last_mode = new_mode
        return new_mode

    def _get_trend_following_signal(self, analyzed_data, latest):
        """Lấy tín hiệu từ chiến lược theo xu hướng"""
        self.logger.debug(f"Chế độ Trend-Following (ADX M15 = {latest.get(f'ADX_{self.adx_length}_M15'):.2f})")
        
        raw_signal, sl, tp = self.trend_strategy.get_signal(analyzed_data)
        
        # Bộ lọc xu hướng M15 bổ sung
        m15_ema_34 = latest.get('M15_EMA_34')
        m15_ema_89 = latest.get('M15_EMA_89')
        
        if m15_ema_34 is not None and m15_ema_89 is not None:
            is_m15_uptrend = (m15_ema_34 > m15_ema_89)
            
            # Chỉ chấp nhận tín hiệu cùng hướng với xu hướng M15
            if (raw_signal == 1 and is_m15_uptrend) or (raw_signal == -1 and not is_m15_uptrend):
                return raw_signal, sl, tp
            else:
                self.logger.debug(f"Tín hiệu Trend-Following bị hủy do ngược xu hướng M15")
                return 0, None, None
        
        return raw_signal, sl, tp

    def _get_mean_reversion_signal(self, analyzed_data, latest):
        """Lấy tín hiệu từ chiến lược đảo chiều"""
        self.logger.debug(f"Chế độ Mean-Reversion (ADX M15 = {latest.get(f'ADX_{self.adx_length}_M15'):.2f})")
        return self.range_strategy.get_signal(analyzed_data)

    def _apply_rsi_filter(self, signal, latest):
        """Áp dụng bộ lọc RSI để tránh tín hiệu giả"""
        rsi_m15 = latest.get('RSI_14_M15')
        if rsi_m15 is None:
            return signal
            
        if signal == 1 and rsi_m15 > self.rsi_overbought:
            self.logger.debug(f"Hủy BUY - RSI quá mua: {rsi_m15:.2f}")
            return 0
        elif signal == -1 and rsi_m15 < self.rsi_oversold:
            self.logger.debug(f"Hủy SELL - RSI quá bán: {rsi_m15:.2f}")
            return 0
            
        return signal

    def _check_volume_filter(self, analyzed_data, latest):
        """Kiểm tra bộ lọc khối lượng"""
        if len(analyzed_data) < 20:
            return True  # Không đủ dữ liệu, bỏ qua bộ lọc
            
        avg_volume = analyzed_data['VOLUME'].tail(20).mean()
        current_volume = latest.get('VOLUME', 0)
        
        if current_volume < avg_volume * self.min_volume_ratio:
            self.logger.debug(f"Khối lượng thấp: {current_volume:.0f} vs TB {avg_volume:.0f}")
            return False
            
        return True

    def _apply_trend_confirmation(self, signal, latest):
        """Xác nhận xu hướng trên nhiều khung thời gian"""
        def get_trend_direction(timeframe):
            ema_fast = latest.get(f'{timeframe}_EMA_34')
            ema_slow = latest.get(f'{timeframe}_EMA_89')
            if ema_fast is None or ema_slow is None:
                return 0
            return 1 if ema_fast > ema_slow else -1

        # Kiểm tra xu hướng trên các khung thời gian
        h1_trend = get_trend_direction('H1')
        m30_trend = get_trend_direction('M30')
        m15_trend = get_trend_direction('M15')

        # Đếm số khung cùng hướng với tín hiệu
        trend_score = 0
        for trend in [h1_trend, m30_trend, m15_trend]:
            if (signal == 1 and trend == 1) or (signal == -1 and trend == -1):
                trend_score += 1

        if trend_score >= self.min_trend_score:
            return signal
        else:
            self.logger.debug(f"Xu hướng không đồng bộ (Điểm: {trend_score}/3)")
            return 0

    def _adjust_sltp_dynamic(self, sl, tp, analyzed_data, latest):
        """Điều chỉnh SL/TP động dựa trên biến động thị trường"""
        atr_m15 = latest.get('ATR_14_M15', 0)
        if atr_m15 <= 0:
            return sl, tp

        # Tính tỷ lệ ATR hiện tại so với trung bình
        avg_atr = analyzed_data['ATR_14_M15'].tail(50).mean()
        if avg_atr <= 0:
            return sl, tp

        atr_ratio = atr_m15 / avg_atr
        
        # Mở rộng SL/TP khi biến động cao
        if atr_ratio > self.atr_adjustment_threshold:
            adjustment_factor = min(1.5, atr_ratio)  # Tối đa 50% mở rộng
            price = latest['CLOSE']
            
            # Tính khoảng cách hiện tại
            if sl < price:  # BUY
                sl_distance = price - sl
                tp_distance = tp - price
            else:  # SELL
                sl_distance = sl - price
                tp_distance = price - tp
            
            # Điều chỉnh
            new_sl_distance = sl_distance * adjustment_factor
            new_tp_distance = tp_distance * adjustment_factor
            
            if sl < price:  # BUY
                sl = price - new_sl_distance
                tp = price + new_tp_distance
            else:  # SELL
                sl = price + new_sl_distance
                tp = price - new_tp_distance
                
            self.logger.debug(f"Điều chỉnh SL/TP +{((adjustment_factor-1)*100):.1f}% (ATR ratio: {atr_ratio:.2f})")
        
        return sl, tp

    def _is_good_trading_time(self):
        """Kiểm tra thời gian giao dịch hợp lệ"""
        if not self.use_time_filter:
            return True
            
        current_time = datetime.now().time()
        start_time = time.fromisoformat(self.trading_hours['start'])
        end_time = time.fromisoformat(self.trading_hours['end'])
        
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        else:
            return current_time >= start_time or current_time <= end_time

    def get_strategy_status(self):
        """Trả về trạng thái hiện tại của chiến lược (cho mục đích debug)"""
        return {
            'current_mode': self.last_mode,
            'adx_thresholds': {
                'trend': self.adx_trend_threshold,
                'range': self.adx_range_threshold,
                'hysteresis': self.adx_hysteresis
            },
            'filters': {
                'rsi': self.use_rsi_filter,
                'volume': self.use_volume_filter,
                'trend_confirmation': self.use_trend_confirmation,
                'dynamic_sltp': self.use_dynamic_sltp
            }
        }