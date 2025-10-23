import pandas as pd
import math
from datetime import datetime

class Backtester:
    """A class to backtest trading strategies."""

    def __init__(self, strategy, data, trading_params, verbose=True):
        self.verbose = verbose
        self.strategy = strategy
        self.data = data
        self.initial_balance = trading_params.get('initial_balance', 1000)
        self.stop_loss_points = trading_params.get('stop_loss_points', 5.0)
        self.take_profit_points = trading_params.get('take_profit_points', 10.0)
        self.max_open_trades = trading_params.get('max_open_trades', 3)
        
        # Breakeven Stop
        self.use_breakeven_stop = trading_params.get('use_breakeven_stop', False)
        self.be_trigger = trading_params.get('breakeven_trigger_points', 5.0)
        self.be_extra = trading_params.get('breakeven_extra_points', 1.0)

        # Trailing Stop (Linear)
        self.use_trailing_stop = trading_params.get('use_trailing_stop', False)
        self.trailing_trigger_step = trading_params.get('trailing_trigger_step', 5.0)
        self.trailing_profit_step = trading_params.get('trailing_profit_step', 1.0)

        # Tiered Trailing Stop (Advanced)
        self.use_tiered_trailing_stop = trading_params.get('use_tiered_trailing_stop', False)
        self.tiered_trailing_stops = trading_params.get('tiered_trailing_stops', [])
        if self.use_tiered_trailing_stop:
            self.tiered_trailing_stops.sort(key=lambda x: x['trigger'], reverse=True)

        # Take Profit Extension
        self.use_tp_extension = trading_params.get('use_tp_extension', False)
        self.tpe_trigger = trading_params.get('tp_extension_trigger_points', 8.0)
        self.tpe_factor = trading_params.get('tp_extension_factor', 1.2)
        self.tpe_sl_target = trading_params.get('tp_extension_sl_target_points', 1.6)

        # Candlestick Exit
        self.use_candlestick_exit = trading_params.get('use_candlestick_exit', False)
        self.bullish_reversal_patterns = ['CDL_HAMMER', 'CDL_INVERTEDHAMMER', 'CDL_PIERCING', 'CDL_MORNINGSTAR', 'CDL_ENGULFING']
        self.bearish_reversal_patterns = ['CDL_HANGINGMAN', 'CDL_SHOOTINGSTAR', 'CDL_EVENINGSTAR', 'CDL_ENGULFING']

        # Weekend Management
        self.close_on_friday = trading_params.get('close_on_friday', False)
        time_str = trading_params.get('friday_close_time', "21:30:00")
        self.friday_close_time = datetime.strptime(time_str, '%H:%M:%S').time()

        self.balance = self.initial_balance
        self.trades = []
        self.open_trades = []

    def run(self):
        if self.verbose:
            print("Starting backtest...")
        
        # State flag to skip trading after Friday close until Monday
        skip_trading = False

        for i in range(1, len(self.data)):
            current_bar = self.data.iloc[i]
            current_timestamp = current_bar.name
            current_slice = self.data.iloc[:i+1]

            # --- Weekend Management Logic ---
            # Reset flag on Monday
            if current_timestamp.dayofweek == 0: # Monday
                if skip_trading: # Log when trading resumes
                    if self.verbose:
                        print(f"--- Trading resumes on Monday [{current_timestamp}] ---")
                    skip_trading = False

            # Check if we need to close positions on Friday
            if self.close_on_friday and current_timestamp.dayofweek == 4: # Friday
                if current_timestamp.time() >= self.friday_close_time:
                    if len(self.open_trades) > 0 and not skip_trading:
                        if self.verbose:
                            print(f"--- Market Close on Friday [{current_timestamp}]. Closing all positions. ---")
                        # Close all open trades
                        trades_to_close_eod = list(self.open_trades)
                        for trade in trades_to_close_eod:
                            self._close_trade(trade, current_bar['CLOSE'], current_timestamp, reason="Friday EOD")
                    skip_trading = True # Set flag to stop trading until Monday
            
            # If flag is set, skip all trading activity
            if skip_trading:
                continue

            # --- Normal Trading Logic ---
            self._check_open_trades(current_slice)
            
            result = self.strategy.get_signal(current_slice)
            signal, dynamic_sl, dynamic_tp = (result, None, None) if isinstance(result, int) else result
            
            if signal != 0 and len(self.open_trades) < self.max_open_trades:
                self._open_trade(signal, current_bar, dynamic_sl, dynamic_tp)

        if self.verbose:
            print("Backtest finished.")
            self.generate_report()

    def _open_trade(self, signal, current_bar, dynamic_sl=None, dynamic_tp=None):
        entry_price = current_bar['CLOSE']
        
        if signal == 1: # BUY
            stop_loss = dynamic_sl if dynamic_sl is not None else entry_price - self.stop_loss_points
            take_profit = dynamic_tp if dynamic_tp is not None else entry_price + self.take_profit_points
        else: # SELL
            stop_loss = dynamic_sl if dynamic_sl is not None else entry_price + self.stop_loss_points
            take_profit = dynamic_tp if dynamic_tp is not None else entry_price - self.take_profit_points

        if take_profit == entry_price:
            return

        trade = {
            'type': 'BUY' if signal == 1 else 'SELL',
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'initial_tp': take_profit, # Store for extension calculation
            'entry_time': current_bar.name,
            'status': 'open',
            'breakeven_applied': False,
            'tp_extended': False,
            'trailing_steps': 0 # Initialize trailing stop counter
        }
        self.open_trades.append(trade)

    def _check_open_trades(self, current_slice):
        current_bar = current_slice.iloc[-1] # Get the latest bar for price checks
        trades_to_close = []
        for trade in self.open_trades:
            # --- Dynamic Exit Logic ---
            if trade['type'] == 'BUY':
                current_profit = current_bar['HIGH'] - trade['entry_price']
                
                # NOTE: The order of these checks matters. Choose one primary stop-loss management strategy.

                # Tiered Trailing Stop (Advanced)
                if self.use_tiered_trailing_stop:
                    for tier in self.tiered_trailing_stops:
                        if current_profit >= tier['trigger']:
                            new_sl = trade['entry_price'] + tier['sl_add']
                            trade['stop_loss'] = max(trade['stop_loss'], new_sl)
                            break # Apply highest applicable tier and stop

                # Linear Trailing Stop
                elif self.use_trailing_stop and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] + sl_improvement
                        trade['stop_loss'] = max(trade['stop_loss'], new_sl)
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and current_profit >= self.be_trigger:
                    new_sl = trade['entry_price'] + self.be_extra
                    trade['stop_loss'] = max(trade['stop_loss'], new_sl)
                    trade['breakeven_applied'] = True

                # Take Profit Extension
                if self.use_tp_extension and not trade['tp_extended'] and current_profit >= self.tpe_trigger:
                    tp_range = abs(trade['initial_tp'] - trade['entry_price'])
                    trade['take_profit'] = trade['entry_price'] + (tp_range * self.tpe_factor)
                    new_sl = trade['entry_price'] + self.tpe_sl_target
                    trade['stop_loss'] = max(trade['stop_loss'], new_sl)
                    trade['tp_extended'] = True

            else: # SELL
                current_profit = trade['entry_price'] - current_bar['LOW']

                # Tiered Trailing Stop (Advanced)
                if self.use_tiered_trailing_stop:
                    for tier in self.tiered_trailing_stops:
                        if current_profit >= tier['trigger']:
                            new_sl = trade['entry_price'] - tier['sl_add']
                            trade['stop_loss'] = min(trade['stop_loss'], new_sl)
                            break

                # Linear Trailing Stop
                elif self.use_trailing_stop and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] - sl_improvement
                        trade['stop_loss'] = min(trade['stop_loss'], new_sl)
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and current_profit >= self.be_trigger:
                    new_sl = trade['entry_price'] - self.be_extra
                    trade['stop_loss'] = min(trade['stop_loss'], new_sl)
                    trade['breakeven_applied'] = True

                # Take Profit Extension
                if self.use_tp_extension and not trade['tp_extended'] and current_profit >= self.tpe_trigger:
                    tp_range = abs(trade['initial_tp'] - trade['entry_price'])
                    trade['take_profit'] = trade['entry_price'] - (tp_range * self.tpe_factor)
                    new_sl = trade['entry_price'] - self.tpe_sl_target
                    trade['stop_loss'] = min(trade['stop_loss'], new_sl)
                    trade['tp_extended'] = True
            
            # --- Candlestick Reversal Exit ---
            if self.use_candlestick_exit:
                if trade['type'] == 'BUY':
                    # Check for bearish reversal patterns to close BUY trade
                    if any(current_bar.get(p, 0) < 0 for p in self.bearish_reversal_patterns):
                        self._close_trade(trade, current_bar['CLOSE'], current_bar.name, reason="Candlestick Reversal")
                        trades_to_close.append(trade)
                else: # SELL
                    # Check for bullish reversal patterns to close SELL trade
                    if any(current_bar.get(p, 0) > 0 for p in self.bullish_reversal_patterns):
                        self._close_trade(trade, current_bar['CLOSE'], current_bar.name, reason="Candlestick Reversal")
                        trades_to_close.append(trade)

            # --- SL/TP Check ---
            if trade['type'] == 'BUY':
                if current_bar['LOW'] <= trade['stop_loss']:
                    self._close_trade(trade, trade['stop_loss'], current_bar.name)
                    trades_to_close.append(trade)
                elif current_bar['HIGH'] >= trade['take_profit']:
                    self._close_trade(trade, trade['take_profit'], current_bar.name)
                    trades_to_close.append(trade)
            elif trade['type'] == 'SELL':
                if current_bar['HIGH'] >= trade['stop_loss']:
                    self._close_trade(trade, trade['stop_loss'], current_bar.name)
                    trades_to_close.append(trade)
                elif current_bar['LOW'] <= trade['take_profit']:
                    self._close_trade(trade, trade['take_profit'], current_bar.name)
                    trades_to_close.append(trade)
        
        self.open_trades = [t for t in self.open_trades if t not in trades_to_close]

    def _close_trade(self, trade, exit_price, exit_time, reason="SL/TP"):
        trade['status'] = 'closed'
        trade['exit_price'] = exit_price
        trade['exit_time'] = exit_time
        
        if trade['type'] == 'BUY':
            pnl = trade['exit_price'] - trade['entry_price']
        else: # SELL
            pnl = trade['entry_price'] - trade['exit_price']
            
        trade['pnl'] = pnl # PnL in points
        trade['exit_reason'] = reason
        self.trades.append(trade)

    def generate_report(self):
        print("\n--- Backtest Report ---")
        if not self.trades:
            print("No trades were executed.")
            return

        report_df = pd.DataFrame(self.trades)
        total_trades = len(report_df)
        wins = report_df[report_df['pnl'] > 0]
        losses = report_df[report_df['pnl'] <= 0]
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = report_df['pnl'].sum()

        print(f"Initial Balance: ${self.initial_balance:.2f}")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {len(wins)}")
        print(f"Losing Trades: {len(losses)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PnL (points): {total_pnl:.2f}")

        # --- Exit Reason Analysis ---
        if 'exit_reason' in report_df.columns:
            print("\n--- Exit Reason Analysis ---")
            exit_reason_counts = report_df['exit_reason'].value_counts()
            print(exit_reason_counts.to_string())

    def get_results(self):
        """Returns a dictionary of the backtest results."""
        if not self.trades:
            return {'total_trades': 0, 'win_rate': 0, 'total_pnl_points': 0}
        
        report_df = pd.DataFrame(self.trades)
        win_rate = (len(report_df[report_df['pnl'] > 0]) / len(report_df)) * 100 if len(report_df) > 0 else 0
        return {'total_trades': len(report_df), 'win_rate': win_rate, 'total_pnl_points': report_df['pnl'].sum()}

    def save_report_to_csv(self, filename):
        """Saves the detailed trade log to a CSV file."""
        if not self.trades:
            if self.verbose:
                print("No trades to save.")
            return

        report_df = pd.DataFrame(self.trades)
        try:
            report_df.to_csv(filename, index=False)
            if self.verbose:
                print(f"Successfully saved trade report to {filename}")
        except Exception as e:
            if self.verbose:
                print(f"Error saving report to {filename}: {e}")
