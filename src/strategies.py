
import pandas as pd
import math

class BaseStrategy:
    def __init__(self, params):
        self.params = params

    def get_signal(self, data):
        raise NotImplementedError("This method should be implemented by subclasses.")

class MultiTimeframeEmaStrategy(BaseStrategy):
    """
    Generates signals based on trend alignment across multiple timeframes (H4, H1, M30, M15).
    Entry is confirmed with a candlestick pattern on the M15 chart.
    """
    def __init__(self, params):
        super().__init__(params)
        self.params = params

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None
            
        latest = analyzed_data.iloc[-1]

        # --- 1. Check Higher Timeframe Trend Alignment ---
        h4_trend = latest.get('H4_TREND', 0)
        h1_trend = latest.get('H1_TREND', 0)
        m30_trend = latest.get('M30_TREND', 0)

        # Bỏ qua H4, chỉ cần H1 và M30 đồng thuận
        is_uptrend_aligned = (h1_trend == 1) and (m30_trend == 1) 
        is_downtrend_aligned = (h1_trend == -1) and (m30_trend == -1)

        # --- 2. Check M15 Execution Timeframe Signal ---
        m15_close_above_ema34 = latest['CLOSE'] > latest['EMA_34']
        m15_close_below_ema34 = latest['CLOSE'] < latest['EMA_34']

        # --- 3. Check for Candlestick Confirmation ---
        bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']
        is_bullish_candle = any(latest.get(p, 0) > 0 for p in bullish_patterns)
        is_bearish_candle = any(latest.get(p, 0) < 0 for p in bearish_patterns)

        # --- 4. Generate Signal ---
        # BUY Signal: All higher TFs are in uptrend, M15 confirms with close > EMA34 and a bullish candle.
        if is_uptrend_aligned and m15_close_above_ema34 and is_bullish_candle:
            return 1, None, None # BUY, SL/TP sẽ được xử lý bởi trading_params

        # SELL Signal: All higher TFs are in downtrend, M15 confirms with close < EMA34 and a bearish candle.
        if is_downtrend_aligned and m15_close_below_ema34 and is_bearish_candle:
            return -1, None, None # SELL, SL/TP sẽ được xử lý bởi trading_params

        return 0, None, None # No signal

class MultiTimeframeEmaFibStrategy(BaseStrategy):
    """
    Generates signals based on trend alignment across multiple timeframes,
    confirmed by a pullback to a Fibonacci retracement level and a candlestick pattern.
    """
    def __init__(self, params):
        super().__init__(params)
        self.fib_lookback_period = params.get('fib_lookback_period', 50)
        self.fib_levels = params.get('fib_levels', [0.5, 0.618])
        self.fib_tolerance = params.get('fib_tolerance', 0.005) # 0.5% tolerance
        self.rsi_oversold_threshold = params.get('rsi_oversold_threshold', 40) # Default for BUY dips
        self.rsi_overbought_threshold = params.get('rsi_overbought_threshold', 60) # Default for SELL rallies
        self.sr_confluence_tolerance = params.get('sr_confluence_tolerance', 0.002) # 0.2% tolerance for S/R confluence

    def _calculate_fib_levels(self, data_slice, trend_direction):
        """Calculates Fibonacci retracement levels based on the recent swing."""
        lookback_data = data_slice.tail(self.fib_lookback_period)
        
        if trend_direction == 1: # Uptrend, looking for pullback to support
            swing_low = lookback_data['LOW'].min()
            swing_high = lookback_data['HIGH'].max()
            price_range = swing_high - swing_low
            if price_range == 0: return None
            return {level: swing_high - (price_range * level) for level in self.fib_levels}
            
        elif trend_direction == -1: # Downtrend, looking for pullback to resistance
            swing_low = lookback_data['LOW'].min()
            swing_high = lookback_data['HIGH'].max()
            price_range = swing_high - swing_low
            if price_range == 0: return None
            return {level: swing_low + (price_range * level) for level in self.fib_levels}
            
        return None

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < self.fib_lookback_period:
            return 0, None, None

        latest = analyzed_data.iloc[-1]

        # --- 1. Check Higher Timeframe Trend Alignment ---
        h4_trend = latest.get('H4_TREND', 0)
        h1_trend = latest.get('H1_TREND', 0)
        is_uptrend_aligned = (h4_trend == 1) and (h1_trend == 1)
        is_downtrend_aligned = (h4_trend == -1) and (h1_trend == -1)

        # --- 2. Candlestick Confirmation ---
        # Using a more comprehensive list of patterns for better signal quality
        bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']
        
        is_bullish_candle = any(latest.get(p, 0) > 0 for p in bullish_patterns)
        is_bearish_candle = any(latest.get(p, 0) < 0 for p in bearish_patterns)

        # --- 3. RSI Filter ---
        current_rsi = latest.get('RSI_14')
        if current_rsi is None or math.isnan(current_rsi): # Ensure RSI is available and valid
            return 0, None, None

        is_rsi_oversold = current_rsi < self.rsi_oversold_threshold
        is_rsi_overbought = current_rsi > self.rsi_overbought_threshold

        # --- 4. Generate Signal with Fibonacci, S/R Confluence, and RSI ---
        if is_uptrend_aligned and is_bullish_candle and is_rsi_oversold: # Added RSI filter
            fib_supports = self._calculate_fib_levels(analyzed_data.iloc[:-1], trend_direction=1)
            if fib_supports:
                for fib_price in fib_supports.values():
                    # Check for confluence with any S/R support level
                    for sr_support_col in ['M15_S', 'H1_S', 'H4_S']:
                        sr_support_level = latest.get(sr_support_col)
                        if sr_support_level and abs(fib_price - sr_support_level) / sr_support_level < self.sr_confluence_tolerance:
                            # Confluence found! Now check if price reacted to this zone.
                            confluence_zone_price = (fib_price + sr_support_level) / 2
                            if abs(latest['LOW'] - confluence_zone_price) / confluence_zone_price < self.fib_tolerance:
                                print(f"BUY Signal Confluence: Fib={fib_price:.2f}, {sr_support_col}={sr_support_level:.2f}, Candle Low={latest['LOW']:.2f}")
                                return 1, None, None # BUY

        if is_downtrend_aligned and is_bearish_candle and is_rsi_overbought: # Added RSI filter
            fib_resistances = self._calculate_fib_levels(analyzed_data.iloc[:-1], trend_direction=-1)
            if fib_resistances:
                for fib_price in fib_resistances.values():
                    # Check for confluence with any S/R resistance level
                    for sr_resistance_col in ['M15_R', 'H1_R', 'H4_R']:
                        sr_resistance_level = latest.get(sr_resistance_col)
                        if sr_resistance_level and abs(fib_price - sr_resistance_level) / sr_resistance_level < self.sr_confluence_tolerance:
                            # Confluence found! Now check if price reacted to this zone.
                            confluence_zone_price = (fib_price + sr_resistance_level) / 2
                            if abs(latest['HIGH'] - confluence_zone_price) / confluence_zone_price < self.fib_tolerance:
                                print(f"SELL Signal Confluence: Fib={fib_price:.2f}, {sr_resistance_col}={sr_resistance_level:.2f}, Candle High={latest['HIGH']:.2f}")
                                return -1, None, None # SELL

        return 0, None, None # No signal

class PriceActionSRStrategy(BaseStrategy):
    """
    Generates signals based on Price Action confirmation from multiple candlestick patterns.
    - Entry: At least 2 candlestick patterns confirm the same direction on M15.
    - SL: Fixed points.
    - TP: Dynamic, based on the nearest S/R level from M15, M30, H1, H4.
    """
    def __init__(self, params):
        super().__init__(params)
        self.min_confirmations = params.get('min_confirmations', 2)
        self.stop_loss_points = params.get('stop_loss_points', 7.0)
        
        self.bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR', 'CDL_3WHITESOLDIERS']
        self.bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR', 'CDL_3BLACKCROWS']

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        entry_price = latest['CLOSE']

        # Count bullish and bearish confirmations
        bullish_confirmations = sum(1 for p in self.bullish_patterns if latest.get(p, 0) > 0)
        bearish_confirmations = sum(1 for p in self.bearish_patterns if latest.get(p, 0) < 0)

        # --- BUY Signal ---
        if bullish_confirmations >= self.min_confirmations:
            # Set fixed SL
            stop_loss = entry_price - self.stop_loss_points
            
            # Find nearest resistance for TP
            resistance_levels = [latest.get(r) for r in ['M15_R', 'M30_R', 'H1_R', 'H4_R'] if latest.get(r) and latest.get(r) > entry_price]
            if not resistance_levels:
                return 0, None, None # No valid TP found
            
            take_profit = min(resistance_levels)
            return 1, stop_loss, take_profit

        # --- SELL Signal ---
        if bearish_confirmations >= self.min_confirmations:
            # Set fixed SL
            stop_loss = entry_price + self.stop_loss_points

            # Find nearest support for TP
            support_levels = [latest.get(s) for s in ['M15_S', 'M30_S', 'H1_S', 'H4_S'] if latest.get(s) and latest.get(s) < entry_price]
            if not support_levels:
                return 0, None, None # No valid TP found

            take_profit = max(support_levels)
            return -1, stop_loss, take_profit

        return 0, None, None # No signal

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

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2] # Nến ngay trước đó

        # --- 1. Xác định xu hướng chính trên M15 ---
        m15_trend = latest.get('M15_TREND_EMA200', 0)
        entry_price = latest['CLOSE']
        
        # --- 2. Xác định tín hiệu giao cắt EMA trên M5 ---
        # Lấy giá trị EMA từ các cột đã được tính toán trong analysis.py
        ema_fast_latest = latest.get(f'M5_EMA_{self.ema_fast_len}')
        ema_slow_latest = latest.get(f'M5_EMA_{self.ema_slow_len}')
        ema_fast_previous = previous.get(f'M5_EMA_{self.ema_fast_len}')
        ema_slow_previous = previous.get(f'M5_EMA_{self.ema_slow_len}')
        
        # Kiểm tra xem các giá trị có hợp lệ không
        if any(v is None for v in [ema_fast_latest, ema_slow_latest, ema_fast_previous, ema_slow_previous]):
            return 0, None, None

        # Tín hiệu MUA: Xu hướng M15 tăng VÀ EMA nhanh cắt lên EMA chậm
        if m15_trend == 1 and ema_fast_previous < ema_slow_previous and ema_fast_latest > ema_slow_latest:
            # Đặt SL dưới đáy gần nhất
            recent_low = analyzed_data['LOW'].iloc[-self.swing_lookback:].min()
            stop_loss = recent_low - 0.2 # Thêm một khoảng đệm nhỏ
            
            # Tính TP dựa trên tỷ lệ R/R
            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * self.rr_ratio)
            return 1, stop_loss, take_profit

        # Tín hiệu BÁN: Xu hướng M15 giảm VÀ EMA nhanh cắt xuống EMA chậm
        if m15_trend == -1 and ema_fast_previous > ema_slow_previous and ema_fast_latest < ema_slow_latest:
            # Đặt SL trên đỉnh gần nhất
            recent_high = analyzed_data['HIGH'].iloc[-self.swing_lookback:].max()
            stop_loss = recent_high + 0.2 # Thêm một khoảng đệm nhỏ

            # Tính TP dựa trên tỷ lệ R/R
            sl_distance = stop_loss - entry_price
            take_profit = entry_price - (sl_distance * self.rr_ratio)
            return -1, stop_loss, take_profit

        return 0, None, None # Không có tín hiệu

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

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0, None, None

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2]
        
        # --- 1. Xác định xu hướng chính trên M15 ---
        m15_trend = latest.get('M15_TREND_EMA200', 0)
        entry_price = latest['CLOSE']

        # --- 2. Lấy giá trị RSI trên M5 ---
        rsi_latest = latest.get('RSI_14')
        rsi_previous = previous.get('RSI_14')

        if rsi_latest is None or rsi_previous is None:
            return 0, None, None

        # --- Tín hiệu MUA: Xu hướng M15 tăng VÀ RSI vừa thoát khỏi vùng quá bán ---
        if m15_trend == 1 and rsi_previous < self.rsi_oversold and rsi_latest > self.rsi_oversold:
            print(f"Tín hiệu MUA: RSI thoát khỏi vùng quá bán ({rsi_previous:.2f} -> {rsi_latest:.2f})")
            recent_low = analyzed_data['LOW'].iloc[-self.swing_lookback:].min()
            stop_loss = recent_low - 0.2
            sl_distance = entry_price - stop_loss
            take_profit = entry_price + (sl_distance * self.rr_ratio)
            return 1, stop_loss, take_profit

        # --- Tín hiệu BÁN: Xu hướng M15 giảm VÀ RSI vừa thoát khỏi vùng quá mua ---
        if m15_trend == -1 and rsi_previous > self.rsi_overbought and rsi_latest < self.rsi_overbought:
            print(f"Tín hiệu BÁN: RSI thoát khỏi vùng quá mua ({rsi_previous:.2f} -> {rsi_latest:.2f})")
            recent_high = analyzed_data['HIGH'].iloc[-self.swing_lookback:].max()
            stop_loss = recent_high + 0.2
            sl_distance = stop_loss - entry_price
            take_profit = entry_price - (sl_distance * self.rr_ratio)
            return -1, stop_loss, take_profit

        return 0, None, None


class SupplyDemandStrategy(BaseStrategy):
    """
    Chiến lược giao dịch dựa trên việc giá kiểm tra lại (retest) các Vùng Cung/Cầu.
    - Tín hiệu MUA: Giá retest Vùng Cầu và có nến xác nhận tăng giá.
    - Tín hiệu BÁN: Giá retest Vùng Cung và có nến xác nhận giảm giá.
    """
    def __init__(self, params):
        super().__init__(params)
        self.retest_tolerance = params.get('retest_tolerance', 0.002) # 0.2% tolerance
        self.confirmation_lookback = params.get('confirmation_lookback', 3) # Chờ xác nhận trong 3 nến
        self.bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        self.bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']
        
        # Biến để lưu trạng thái retest
        self.demand_retested_in_last_x_bars = 0
        self.supply_retested_in_last_x_bars = 0

    def get_signal(self, analyzed_data):
        if len(analyzed_data) < self.confirmation_lookback:
            return 0, None, None

        latest = analyzed_data.iloc[-1]

        # --- Cập nhật trạng thái Retest ---
        nearest_demand_level = latest.get('NEAREST_DEMAND')
        nearest_supply_level = latest.get('NEAREST_SUPPLY')

        # Kiểm tra retest Vùng Cầu
        if nearest_demand_level and not pd.isna(nearest_demand_level):
            if latest['LOW'] <= nearest_demand_level * (1 + self.retest_tolerance):
                self.demand_retested_in_last_x_bars = self.confirmation_lookback
        else:
            self.demand_retested_in_last_x_bars = max(0, self.demand_retested_in_last_x_bars - 1)

        # Kiểm tra retest Vùng Cung
        if nearest_supply_level and not pd.isna(nearest_supply_level):
            if latest['HIGH'] >= nearest_supply_level * (1 - self.retest_tolerance):
                self.supply_retested_in_last_x_bars = self.confirmation_lookback
        else:
            self.supply_retested_in_last_x_bars = max(0, self.supply_retested_in_last_x_bars - 1)

        # --- Tìm tín hiệu dựa trên trạng thái đã Retest ---
        # Tín hiệu MUA: Đã retest Vùng Cầu trong X nến gần đây VÀ nến hiện tại là nến xác nhận tăng
        if self.demand_retested_in_last_x_bars > 0:
            is_bullish_candle = any(latest.get(p, 0) > 0 for p in self.bullish_patterns)
            if is_bullish_candle:
                print(f"Tín hiệu MUA: Giá retest Vùng Cầu tại ~{nearest_demand_level:.2f}")
                self.demand_retested_in_last_x_bars = 0 # Reset trạng thái sau khi vào lệnh
                return 1, None, None # BUY

        # Tín hiệu BÁN: Đã retest Vùng Cung trong X nến gần đây VÀ nến hiện tại là nến xác nhận giảm
        if self.supply_retested_in_last_x_bars > 0:
            is_bearish_candle = any(latest.get(p, 0) < 0 for p in self.bearish_patterns)
            if is_bearish_candle:
                print(f"Tín hiệu BÁN: Giá retest Vùng Cung tại ~{nearest_supply_level:.2f}")
                self.supply_retested_in_last_x_bars = 0 # Reset trạng thái sau khi vào lệnh
                return -1, None, None # SELL

        return 0, None, None # Không có tín hiệu

class MultiEmaPAStochStrategy(BaseStrategy):
    """
    A confluence strategy that uses EMAs for trend, S/R zones for value,
    and Stochastic for entry timing.
    - M15 Trend: EMA 34 vs EMA 89
    - H1 Trend: Price vs EMA 200
    - Entry Zone: Reaction to S/R levels
    - Entry Trigger: Stochastic Oscillator
    """
    def __init__(self, params):
        super().__init__(params)
        # Strategy parameters with defaults
        self.sr_retest_tolerance = params.get('sr_retest_tolerance', 0.001) # 0.1% tolerance for S/R retest
        self.stoch_oversold = params.get('stoch_oversold', 30)
        self.stoch_overbought = params.get('stoch_overbought', 70)
        # Note: The analysis script provides STOCHk_14_3_3 and STOCHd_14_3_3. We use these.
        self.stoch_k_col = 'STOCHk_14_3_3'
        self.stoch_d_col = 'STOCHd_14_3_3'
        
        # Parameters for SL/TP calculation
        self.swing_lookback_sl = params.get('swing_lookback_sl', 10)
        self.rr_ratio = params.get('rr_ratio', 2.0) # Default Risk/Reward ratio of 2

        # State variables to track setups
        self.setup_lookback = params.get('setup_lookback', 3) # Look for a setup in the last 3 candles
        self.buy_setup_active = False
        self.sell_setup_active = False

    def get_signal(self, analyzed_data: pd.DataFrame):
        if len(analyzed_data) < 2:
            return 0, None, None
    
        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2]

        # --- 1. Trend Filter (EMA) ---
        m15_ema34 = latest.get('EMA_34')
        m15_ema89 = latest.get('EMA_89')
        h1_trend = latest.get('H1_TREND', 0)
    
        # --- 2. Stochastic Filter ---
        stoch_k_latest = latest.get(self.stoch_k_col)
        stoch_d_latest = latest.get(self.stoch_d_col)
        stoch_k_previous = previous.get(self.stoch_k_col)
        stoch_d_previous = previous.get(self.stoch_d_col)
    
        if any(pd.isna(v) for v in [m15_ema34, m15_ema89, stoch_k_latest, stoch_d_latest, stoch_k_previous, stoch_d_previous]):
            return 0, None, None # Not enough data
    
        is_uptrend = (m15_ema34 > m15_ema89) and (h1_trend == 1)
        is_downtrend = (m15_ema34 < m15_ema89) and (h1_trend == -1)
    
        # Stochastic crossover conditions
        stoch_bullish_crossover = stoch_k_previous < stoch_d_previous and stoch_k_latest > stoch_d_latest
        stoch_bearish_crossover = stoch_k_previous > stoch_d_previous and stoch_k_latest < stoch_d_latest
    
        # --- 3. Setup Confirmation: Look for S/R reaction in recent past ---
        self.buy_setup_active = False
        self.sell_setup_active = False

        # Check for a setup within the last `setup_lookback` candles
        for i in range(1, self.setup_lookback + 1):
            if len(analyzed_data) <= i: break
            bar = analyzed_data.iloc[-i]

            if is_uptrend:
                support_levels = [bar.get(s) for s in ['M15_S', 'H1_S', 'H4_S'] if bar.get(s) and not pd.isna(bar.get(s))]
                for support in support_levels:
                    if abs(bar['LOW'] - support) / support < self.sr_retest_tolerance:
                        self.buy_setup_active = True
                        break
            
            if is_downtrend:
                resistance_levels = [bar.get(r) for r in ['M15_R', 'H1_R', 'H4_R'] if bar.get(r) and not pd.isna(bar.get(r))]
                for resistance in resistance_levels:
                    if abs(bar['HIGH'] - resistance) / resistance < self.sr_retest_tolerance:
                        self.sell_setup_active = True
                        break
            
            if self.buy_setup_active or self.sell_setup_active:
                break # Found a setup, no need to look further back

        # --- 4. Trigger Signal: Stochastic Crossover + Price Action on the latest candle ---
        bullish_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR']
        bearish_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR']
        
        # BUY Signal: Uptrend + Recent S/R Bounce Setup + Stochastic Oversold Crossover + Bullish PA
        if self.buy_setup_active and stoch_k_latest < self.stoch_oversold and stoch_bullish_crossover:
            if any(latest.get(p, 0) > 0 for p in bullish_patterns):
                print(f"BUY Signal: Setup Confirmed, Stoch Cross ({stoch_k_latest:.1f}) with Bullish PA")
                # Calculate SL/TP
                entry_price = latest['CLOSE']
                recent_low = analyzed_data['LOW'].iloc[-self.swing_lookback_sl:].min() # Correctly find recent low
                stop_loss = recent_low - 0.2 # SL is BELOW the recent low
                sl_distance = entry_price - stop_loss
                take_profit = entry_price + (sl_distance * self.rr_ratio)
                return 1, stop_loss, take_profit # Return correct values

        # SELL Signal: Downtrend + Recent S/R Bounce Setup + Stochastic Overbought Crossover + Bearish PA
        if self.sell_setup_active and stoch_k_latest > self.stoch_overbought and stoch_bearish_crossover:
            if any(latest.get(p, 0) < 0 for p in bearish_patterns):
                print(f"SELL Signal: Setup Confirmed, Stoch Cross ({stoch_k_latest:.1f}) with Bearish PA")
                # Calculate SL/TP
                entry_price = latest['CLOSE']
                recent_high = analyzed_data['HIGH'].iloc[-self.swing_lookback_sl:].max() # Correctly find recent high
                stop_loss = recent_high + 0.2 # SL is ABOVE the recent high
                sl_distance = stop_loss - entry_price
                take_profit = entry_price - (sl_distance * self.rr_ratio)
                return -1, stop_loss, take_profit # Return correct values
    
        return 0, None, None # No signal
