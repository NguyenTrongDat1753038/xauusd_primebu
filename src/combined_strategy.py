
from strategies import BaseStrategy, ScalpingEmaCrossoverStrategy, ScalpingRsiPullbackStrategy

class CombinedScalpingStrategy(BaseStrategy):
    """
    A combined strategy that prioritizes EMA crossover signals and falls back to RSI pullback signals.
    """
    def __init__(self, params):
        super().__init__(params)
        self.ema_strategy = ScalpingEmaCrossoverStrategy(params.get('ScalpingEmaCrossoverStrategy', {}))
        self.rsi_strategy = ScalpingRsiPullbackStrategy(params.get('ScalpingRsiPullbackStrategy', {}))
        self.ema_strength_threshold = params.get('ema_strength_threshold', 0.0)

    def get_signal(self, analyzed_data):
        # 1. Get EMA signal
        ema_signal, ema_sl, ema_tp = self.ema_strategy.get_signal(analyzed_data)

        if ema_signal != 0:
            # 2. Calculate EMA signal strength
            strength = self._calculate_ema_strength(analyzed_data)

            # 3. If EMA signal is strong enough, use it
            if strength >= self.ema_strength_threshold:
                return ema_signal, ema_sl, ema_tp

        # 4. If no strong EMA signal, get RSI signal
        rsi_signal, rsi_sl, rsi_tp = self.rsi_strategy.get_signal(analyzed_data)
        return rsi_signal, rsi_sl, rsi_tp

    def _calculate_ema_strength(self, analyzed_data):
        if len(analyzed_data) < 2:
            return 0

        latest = analyzed_data.iloc[-1]
        previous = analyzed_data.iloc[-2]

        ema_fast_latest = latest.get(f'M5_EMA_{self.ema_strategy.ema_fast_len}')
        ema_slow_latest = latest.get(f'M5_EMA_{self.ema_strategy.ema_slow_len}')
        ema_fast_previous = previous.get(f'M5_EMA_{self.ema_strategy.ema_fast_len}')
        ema_slow_previous = previous.get(f'M5_EMA_{self.ema_strategy.ema_slow_len}')

        if any(v is None for v in [ema_fast_latest, ema_slow_latest, ema_fast_previous, ema_slow_previous]):
            return 0

        slope_fast = ema_fast_latest - ema_fast_previous
        slope_slow = ema_slow_latest - ema_slow_previous

        return abs(slope_fast - slope_slow)
