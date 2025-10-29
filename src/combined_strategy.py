
from strategies import BaseStrategy, ScalpingEmaCrossoverStrategy, ScalpingRsiPullbackStrategy
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

    def get_signal(self, analyzed_data: pd.DataFrame):
        """
        Generates a signal based on a voting system.
        Returns the signal from the first strategy that voted if multiple strategies agree.
        """
        buy_votes = 0
        sell_votes = 0
        
        # --- Vote 1: EMA Crossover Strategy ---
        ema_signal, ema_sl, ema_tp = self.ema_strategy.get_signal(analyzed_data)
        if ema_signal == 1:
            buy_votes += 1
        elif ema_signal == -1:
            sell_votes += 1

        # --- Vote 2: RSI Pullback Strategy ---
        rsi_signal, rsi_sl, rsi_tp = self.rsi_strategy.get_signal(analyzed_data)
        if rsi_signal == 1:
            buy_votes += 1
        elif rsi_signal == -1:
            sell_votes += 1

        # --- Decision Making ---
        
        # Check for BUY signal
        if buy_votes >= self.required_votes:
            print(f"Combined BUY Signal: {buy_votes} votes received.")            
            # Logic to choose the safest (lowest) Stop Loss among all voting signals
            final_sl = None
            if ema_signal == 1 and rsi_signal == 1:
                final_sl = min(ema_sl, rsi_sl) if ema_sl is not None and rsi_sl is not None else (ema_sl or rsi_sl)
            elif ema_signal == 1:
                final_sl = ema_sl
            else: # rsi_signal must be 1
                final_sl = rsi_sl
            
            # For TP, we can take the average or the closest one. Let's take the closest for now.
            final_tp = min(filter(None, [ema_tp, rsi_tp])) if any(v is not None for v in [ema_tp, rsi_tp]) else None
            return 1, final_sl, final_tp

        # Check for SELL signal
        if sell_votes >= self.required_votes:
            print(f"Combined SELL Signal: {sell_votes} votes received.")
            # Logic to choose the safest (highest) Stop Loss
            final_sl = None
            if ema_signal == -1 and rsi_signal == -1:
                final_sl = max(ema_sl, rsi_sl) if ema_sl is not None and rsi_sl is not None else (ema_sl or rsi_sl)
            elif ema_signal == -1:
                final_sl = ema_sl
            else: # rsi_signal must be -1
                final_sl = rsi_sl

            final_tp = max(filter(None, [ema_tp, rsi_tp])) if any(v is not None for v in [ema_tp, rsi_tp]) else None
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
