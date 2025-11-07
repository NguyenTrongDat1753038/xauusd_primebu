
from .base_strategy import BaseStrategy
from .scalping_ema_crossover_strategy import ScalpingEmaCrossoverStrategy
from .scalping_rsi_pullback_strategy import ScalpingRsiPullbackStrategy
import pandas as pd

class CombinedScalpingStrategy(BaseStrategy):
    """
    A combined strategy that uses a voting system between different scalping signals.
    - EMA Crossover gives one vote.
    - RSI Pullback gives one vote.
    - A trade is triggered if the number of votes meets the required threshold.
    """
    def __init__(self, params):
        super().__init__(params)
        self.ema_strategy = ScalpingEmaCrossoverStrategy(params.get('ScalpingEmaCrossoverStrategy', {}))
        self.rsi_strategy = ScalpingRsiPullbackStrategy(params.get('ScalpingRsiPullbackStrategy', {}))
        # The number of confirmations required to generate a signal. E.g., 1 for any signal, 2 for both.
        self.required_votes = params.get('required_votes', 1)

        # --- Thêm logic bỏ phiếu bằng mô hình nến ---
        self.use_candle_vote = params.get('use_candle_vote', False)
        self.bullish_patterns = params.get('bullish_patterns', ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_ENGULFING', 'CDL_PIERCING', 'CDL_MORNINGSTAR'])
        self.bearish_patterns = params.get('bearish_patterns', ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_ENGULFING', 'CDL_EVENINGSTAR'])


    def get_signal(self, analyzed_data: pd.DataFrame):
        """
        Generates a signal based on a voting system.
        Returns the signal from the first strategy that voted if multiple strategies agree.
        """
        buy_votes = 0
        sell_votes = 0
        signals_data = [] # Lưu trữ (signal, sl, tp) của các chiến lược đã vote
        
        # --- Vote 1: EMA Crossover Strategy ---
        ema_signal, ema_sl, ema_tp = self.ema_strategy.get_signal(analyzed_data)
        if ema_signal == 1:
            buy_votes += 1
        elif ema_signal == -1:
            sell_votes += 1
        if ema_signal != 0:
            signals_data.append({'signal': ema_signal, 'sl': ema_sl, 'tp': ema_tp, 'source': 'EMA'})

        # --- Vote 2: RSI Pullback Strategy ---
        rsi_signal, rsi_sl, rsi_tp = self.rsi_strategy.get_signal(analyzed_data)
        if rsi_signal == 1:
            buy_votes += 1
        elif rsi_signal == -1:
            sell_votes += 1
        if rsi_signal != 0:
            signals_data.append({'signal': rsi_signal, 'sl': rsi_sl, 'tp': rsi_tp, 'source': 'RSI'})

        # --- Vote 3: Candlestick Pattern Strategy ---
        if self.use_candle_vote:
            latest = analyzed_data.iloc[-1]
            is_bullish_candle = any(latest.get(p, 0) > 0 for p in self.bullish_patterns)
            is_bearish_candle = any(latest.get(p, 0) < 0 for p in self.bearish_patterns)
            if is_bullish_candle:
                buy_votes += 1
                # Nến không tự cung cấp SL/TP, nên ta không thêm vào signals_data
            elif is_bearish_candle:
                sell_votes += 1

        # --- Decision Making ---
        
        # Check for BUY signal
        if buy_votes >= self.required_votes:
            print(f"Combined BUY Signal: {buy_votes} votes received.")
            # Lấy tất cả SL/TP từ các tín hiệu MUA đã bỏ phiếu
            buy_signals = [s for s in signals_data if s['signal'] == 1]
            if not buy_signals: # Nếu chỉ có nến vote, không có SL/TP
                return 0, None, None
            
            # Chọn SL an toàn nhất (thấp nhất) và TP gần nhất (dễ đạt nhất)
            valid_sls = [s['sl'] for s in buy_signals if s['sl'] is not None]
            valid_tps = [s['tp'] for s in buy_signals if s['tp'] is not None]

            if not valid_sls or not valid_tps: return 0, None, None

            final_sl = min(valid_sls)
            final_tp = min(valid_tps)
            return 1, final_sl, final_tp

        # Check for SELL signal
        if sell_votes >= self.required_votes:
            print(f"Combined SELL Signal: {sell_votes} votes received.")
            # Lấy tất cả SL/TP từ các tín hiệu BÁN đã bỏ phiếu
            sell_signals = [s for s in signals_data if s['signal'] == -1]
            if not sell_signals: # Nếu chỉ có nến vote, không có SL/TP
                return 0, None, None

            # Chọn SL an toàn nhất (cao nhất) và TP gần nhất (dễ đạt nhất)
            valid_sls = [s['sl'] for s in sell_signals if s['sl'] is not None]
            valid_tps = [s['tp'] for s in sell_signals if s['tp'] is not None]

            if not valid_sls or not valid_tps: return 0, None, None

            final_sl = max(valid_sls)
            final_tp = max(valid_tps) # TP của lệnh bán là giá thấp hơn, nên max là gần nhất
            return -1, final_sl, final_tp

        # No signal
        return 0, None, None

    # The _calculate_ema_strength method is no longer needed with the voting system.
    # def _calculate_ema_strength(self, analyzed_data):
    #     if len(analyzed_data) < 2:
    #         return 0

    #     latest = analyzed_data.iloc[-1]
    #     previous = analyzed_data.iloc[-2]

    #     ema_fast_latest = latest.get(f'M5_EMA_{self.ema_strategy.ema_fast_len}')
    #     ema_slow_latest = latest.get(f'M5_EMA_{self.ema_strategy.ema_slow_len}')
    #     ema_fast_previous = previous.get(f'M5_EMA_{self.ema_strategy.ema_fast_len}')
    #     ema_slow_previous = previous.get(f'M5_EMA_{self.ema_strategy.ema_slow_len}')

    #     if any(v is None for v in [ema_fast_latest, ema_slow_latest, ema_fast_previous, ema_slow_previous]):
    #         return 0

    #     slope_fast = ema_fast_latest - ema_fast_previous
    #     slope_slow = ema_slow_latest - ema_slow_previous

    #     return abs(slope_fast - slope_slow)
