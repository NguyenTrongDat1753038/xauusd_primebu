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
        self.spread = trading_params.get('spread', 0.2) # Giả định spread là 0.2 USD (20 pips)
        self.max_open_trades = trading_params.get('max_open_trades', 3)

        # Position Sizing
        self.use_dynamic_sizing = trading_params.get('use_dynamic_sizing', False)
        self.risk_percent = trading_params.get('risk_percent', 1.0) # Lấy risk_percent (ví dụ: 1.0 cho 1%)
        self.contract_size = trading_params.get('contract_size', 100.0) # Default to 100 for XAUUSD
        self.default_position_size = trading_params.get('default_position_size', 0.1) # Default lot size if not dynamic
        self.min_position_size = trading_params.get('min_position_size', 0.01) # Minimum lot size
        self.max_position_size = trading_params.get('max_position_size', 1.0) # Maximum lot size
        self.min_sl_distance_points = trading_params.get('min_sl_distance_points', 0.5) # Default to 0.5 USD for XAUUSD
        self.target_sl_distance_points = trading_params.get('target_sl_distance_points', 4.0) # Target SL distance for safer lot sizing
        
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
        
        # Determine initial Stop Loss based on signal and dynamic/fixed values
        if signal == 1: # BUY
            stop_loss = dynamic_sl if dynamic_sl is not None else entry_price - self.stop_loss_points
            take_profit = dynamic_tp if dynamic_tp is not None else entry_price + self.take_profit_points
        else: # SELL
            stop_loss = dynamic_sl if dynamic_sl is not None else entry_price + self.stop_loss_points
            take_profit = dynamic_tp if dynamic_tp is not None else entry_price - self.take_profit_points

        # --- Enforce minimum Stop Loss distance ---
        # This prevents extremely tight SLs leading to excessively large lot sizes.
        # It ensures that the SL is always at least `min_sl_distance_points` away from the entry price.
        current_sl_distance = abs(entry_price - stop_loss)
        if current_sl_distance < self.min_sl_distance_points:
            if self.verbose:
                print(f"Warning: Calculated SL distance ({current_sl_distance:.4f}) is too small. Adjusting SL to enforce minimum distance ({self.min_sl_distance_points:.2f}).")
            if signal == 1: # BUY trade: SL must be below entry price
                stop_loss = entry_price - self.min_sl_distance_points
            else: # SELL trade: SL must be above entry price
                stop_loss = entry_price + self.min_sl_distance_points
            
            # Note: If TP was dynamically calculated based on the original SL distance,
            # it might become disproportionate after SL adjustment. For simplicity,
            # we keep the original TP. A more advanced approach might recalculate TP.


        if take_profit == entry_price: # Avoid trades with zero TP
            return

        # Calculate position size (lot size)
        position_size = 0.0 # Default to 0, will be updated
        final_stop_loss = stop_loss # Start with the strategy's SL (potentially adjusted by min_sl_distance_points)

        if self.use_dynamic_sizing:
            risk_amount = self.balance * (self.risk_percent / 100.0)
            
            # --- New Logic: Calculate two potential lot sizes and choose the safer one ---

            # 1. Lot size based on the strategy's dynamic SL (which might have been adjusted by min_sl_distance_points)
            strategy_sl_distance = abs(entry_price - stop_loss)
            lot_from_strategy_sl = risk_amount / (strategy_sl_distance * self.contract_size) if strategy_sl_distance > 0 else float('inf')

            # 2. Lot size based on a "target" (safer) SL distance
            lot_from_target_sl = risk_amount / (self.target_sl_distance_points * self.contract_size)

            # Chọn lot size NHỎ HƠN (an toàn hơn) trong hai trường hợp
            raw_position_size = min(lot_from_strategy_sl, lot_from_target_sl)

            # Nếu chúng ta chọn lot size từ target SL (tức là nó nhỏ hơn lot size từ SL của chiến lược),
            # chúng ta phải điều chỉnh SL thực tế để phù hợp với rủi ro đã chọn.
            if raw_position_size < lot_from_strategy_sl:
                if self.verbose:
                    # In ra thông báo rõ ràng hơn về việc điều chỉnh
                    print(f"Info: Strategy SL ({strategy_sl_distance:.2f}) dẫn đến lot lớn hơn. Sử dụng Target SL ({self.target_sl_distance_points:.2f}) để tính lot an toàn hơn.")
                    print(f"      Lot từ Strategy SL: {lot_from_strategy_sl:.2f}, Lot từ Target SL: {lot_from_target_sl:.2f}. Chọn lot: {raw_position_size:.2f}.")
                # Recalculate the SL to match the chosen lot size and risk amount
                # risk_amount = lot * sl_distance * contract_size  =>  sl_distance = risk_amount / (lot * contract_size)
                new_sl_distance = risk_amount / (raw_position_size * self.contract_size)
                if signal == 1: # BUY
                    final_stop_loss = entry_price - new_sl_distance
                else: # SELL
                    final_stop_loss = entry_price + new_sl_distance
            else:
                # Nếu lot size từ SL của chiến lược được chọn (vì nó nhỏ hơn hoặc bằng target SL lot),
                # thì `final_stop_loss` (đã được gán từ `stop_loss` ban đầu) là chính xác.
                pass

            # Apply min/max position size limits
            position_size = max(self.min_position_size, min(raw_position_size, self.max_position_size))
            position_size = round(position_size, 2)
        else:
            position_size = self.default_position_size

        # Ensure position size is not zero or negative
        if position_size <= 0:
            if self.verbose:
                print(f"Warning: Calculated position size is zero or negative ({position_size:.2f}). Skipping trade.")
                return

        trade = {
            'type': 'BUY' if signal == 1 else 'SELL',
            'entry_price': entry_price,
            'stop_loss': final_stop_loss,
            'take_profit': take_profit,
            'position_size': position_size, # Store calculated position size
            'initial_tp': take_profit, # Store for extension calculation
            'entry_time': current_bar.name,
            'status': 'open',
            'breakeven_applied': False,
            'tp_extended': False,
            'trailing_steps': 0, # Initialize trailing stop counter
            'sl_reason': 'Initial'
        }
        self.open_trades.append(trade)

    def _check_open_trades_old(self, current_slice):
        # This method should only manage existing open trades.
        # Lot size calculation should happen in _open_trade.
        # The previous code block for position_size calculation was misplaced here.
        pass

    def _check_open_trades(self, current_slice):
        current_bar = current_slice.iloc[-1] # Get the latest bar for price checks
        # Thay vì đóng lệnh ngay, chúng ta thu thập thông tin để đóng sau
        # Điều này tránh việc một lệnh bị đóng nhiều lần với các lý do khác nhau trong cùng một tick
        trades_to_process_for_closure = []

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
                            if new_sl > trade['stop_loss']:
                                trade['stop_loss'] = new_sl
                                trade['sl_reason'] = 'Tiered Trailing'
                            break # Apply highest applicable tier and stop

                # Linear Trailing Stop
                elif self.use_trailing_stop and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] + sl_improvement
                        if new_sl > trade['stop_loss']:
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = 'Linear Trailing'
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and current_profit >= self.be_trigger:
                    new_sl = trade['entry_price'] + self.be_extra
                    print(f"[{current_bar.name}] Applying Breakeven for BUY trade #{self.trades.index(trade) if trade in self.trades else 'new'}. New SL: {new_sl}")
                    if new_sl > trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'Breakeven'
                    trade['breakeven_applied'] = True

                # Take Profit Extension
                if self.use_tp_extension and not trade['tp_extended'] and current_profit >= self.tpe_trigger:
                    tp_range = abs(trade['initial_tp'] - trade['entry_price'])
                    trade['take_profit'] = trade['entry_price'] + (tp_range * self.tpe_factor)
                    new_sl = trade['entry_price'] + self.tpe_sl_target
                    if new_sl > trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'TP Extension'
                    trade['tp_extended'] = True

            else: # SELL
                current_profit = trade['entry_price'] - current_bar['LOW']

                # Tiered Trailing Stop (Advanced)
                if self.use_tiered_trailing_stop:
                    for tier in self.tiered_trailing_stops:
                        if current_profit >= tier['trigger']:
                            new_sl = trade['entry_price'] - tier['sl_add']
                            if new_sl < trade['stop_loss']:
                                trade['stop_loss'] = new_sl
                                trade['sl_reason'] = 'Tiered Trailing'
                            break

                # Linear Trailing Stop
                elif self.use_trailing_stop and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] - sl_improvement
                        if new_sl < trade['stop_loss']:
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = 'Linear Trailing'
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and current_profit >= self.be_trigger:
                    new_sl = trade['entry_price'] - self.be_extra
                    print(f"[{current_bar.name}] Applying Breakeven for SELL trade #{self.trades.index(trade) if trade in self.trades else 'new'}. New SL: {new_sl}")
                    if new_sl < trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'Breakeven'
                    trade['breakeven_applied'] = True

                # Take Profit Extension
                if self.use_tp_extension and not trade['tp_extended'] and current_profit >= self.tpe_trigger:
                    tp_range = abs(trade['initial_tp'] - trade['entry_price'])
                    trade['take_profit'] = trade['entry_price'] - (tp_range * self.tpe_factor)
                    new_sl = trade['entry_price'] - self.tpe_sl_target
                    if new_sl < trade['stop_loss']:
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'TP Extension'
                    trade['tp_extended'] = True
            
            # --- Candlestick Reversal Exit ---
            if self.use_candlestick_exit:
                if trade['type'] == 'BUY':
                    # Check for bearish reversal patterns to close BUY trade
                    if any(current_bar.get(p, 0) < 0 for p in self.bearish_reversal_patterns) and trade not in [t[0] for t in trades_to_process_for_closure]:
                        trades_to_process_for_closure.append((trade, current_bar['CLOSE'], "Candlestick Reversal"))
                        continue
                else: # SELL
                    # Check for bullish reversal patterns to close SELL trade
                    if any(current_bar.get(p, 0) > 0 for p in self.bullish_reversal_patterns) and trade not in [t[0] for t in trades_to_process_for_closure]:
                        trades_to_process_for_closure.append((trade, current_bar['CLOSE'], "Candlestick Reversal"))
                        continue

            # --- SL/TP Check ---
            if trade['type'] == 'BUY':
                # Ưu tiên kiểm tra SL trước
                if current_bar['LOW'] <= trade['stop_loss'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    reason = trade.get('sl_reason', 'Stop Loss')
                    if reason == 'Initial':
                        reason = 'Stop Loss'
                    trades_to_process_for_closure.append((trade, trade['stop_loss'], reason))
                    continue
                # Chỉ kiểm tra TP nếu SL không bị chạm
                elif current_bar['HIGH'] >= trade['take_profit'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    trades_to_process_for_closure.append((trade, trade['take_profit'], "Take Profit"))
                    continue
            elif trade['type'] == 'SELL':
                if current_bar['HIGH'] >= trade['stop_loss'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    reason = trade.get('sl_reason', 'Stop Loss')
                    if reason == 'Initial':
                        reason = 'Stop Loss'
                    trades_to_process_for_closure.append((trade, trade['stop_loss'], reason))
                    continue
                elif current_bar['LOW'] <= trade['take_profit'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    trades_to_process_for_closure.append((trade, trade['take_profit'], "Take Profit"))
                    continue
        
        # Bây giờ, xử lý đóng các lệnh đã được xác định
        for trade_to_close, exit_price, reason in trades_to_process_for_closure:
            self._close_trade(trade_to_close, exit_price, current_bar.name, reason=reason)
            if trade_to_close in self.open_trades: # Đảm bảo lệnh vẫn còn trong danh sách mở
                self.open_trades.remove(trade_to_close)

    def _close_trade(self, trade, exit_price, exit_time, reason="Take Profit"):
        trade['status'] = 'closed'
        trade['exit_price'] = exit_price
        trade['exit_time'] = exit_time
        
        if trade['type'] == 'BUY':
            # Khi đóng lệnh BUY, chúng ta bán ở giá BID (thấp hơn)
            pnl = (exit_price - self.spread / 2) - trade['entry_price']
        else: # SELL
            # Khi đóng lệnh SELL, chúng ta mua ở giá ASK (cao hơn)
            pnl = trade['entry_price'] - (exit_price + self.spread / 2)
        
        pnl_currency = pnl * trade.get('position_size', 0) * self.contract_size # Calculate monetary PnL
            
        trade['pnl'] = pnl # PnL in points
        trade['pnl_currency'] = pnl_currency
        trade['exit_reason'] = reason
        self.trades.append(trade)

    def generate_report(self):
        print("\n--- Backtest Report ---")
        if not self.trades:
            print("No trades were executed.")
            return

        report_df = pd.DataFrame(self.trades)
        total_trades = len(report_df) # Total trades executed
        wins = report_df[report_df['pnl_currency'] > 0] # Winning trades based on currency PnL
        losses = report_df[report_df['pnl_currency'] <= 0] # Losing trades based on currency PnL
        
        win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl_points = report_df['pnl'].sum() # Sum of PnL in points
        total_pnl_currency = report_df['pnl_currency'].sum() # Sum of PnL in currency

        final_balance = self.initial_balance + total_pnl_currency # Final balance

        print(f"Initial Balance: ${self.initial_balance:.2f}")
        print(f"Total Trades: {total_trades}")
        print(f"Winning Trades: {len(wins)}")
        print(f"Losing Trades: {len(losses)}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PnL (points): {total_pnl_points:.2f}")
        print(f"Total PnL (currency): ${total_pnl_currency:.2f}")
        print(f"Final Balance: ${final_balance:.2f}")

        # --- Exit Reason Analysis ---
        if 'exit_reason' in report_df.columns:
            print("\n--- Exit Reason Analysis ---")
            exit_reason_counts = report_df['exit_reason'].value_counts()
            print(exit_reason_counts.to_string())

    def get_results(self):
        """Returns a dictionary of the backtest results."""
        if not self.trades:
            return {'total_trades': 0, 'win_rate': 0, 'total_pnl_points': 0, 'total_pnl_currency': 0, 'final_balance': self.initial_balance}
        
        report_df = pd.DataFrame(self.trades)
        win_rate = (len(report_df[report_df['pnl_currency'] > 0]) / len(report_df)) * 100 if len(report_df) > 0 else 0
        total_pnl_currency = report_df['pnl_currency'].sum()
        final_balance = self.initial_balance + total_pnl_currency
        return {'total_trades': len(report_df), 'win_rate': win_rate, 'total_pnl_points': report_df['pnl'].sum(), 'total_pnl_currency': total_pnl_currency, 'final_balance': final_balance}

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
