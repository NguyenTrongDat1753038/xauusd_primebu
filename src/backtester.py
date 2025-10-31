import pandas as pd
import math
import uuid
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
        self.target_sl_distance_points = trading_params.get('target_sl_distance_points', 4.0)
        
        # Dynamic Risk Limits per trade (as a percentage of balance)
        self.min_risk_percent = trading_params.get('min_risk_percent', 1.5) # Min risk per trade
        self.max_risk_percent = trading_params.get('max_risk_percent', 4.0) # Max risk per trade (ceiling)
        
        # Drawdown Reducer
        self.drawdown_reducer_tiers = sorted(trading_params.get('drawdown_reducer_tiers', []), key=lambda x: x['threshold_percent'], reverse=True)

        # Circuit Breaker
        self.cb_config = trading_params.get('circuit_breaker', {'enabled': False})
        self.use_circuit_breaker = self.cb_config.get('enabled', False)
        self.daily_loss_limit_percent = self.cb_config.get('daily_loss_limit_percent', 8.0)
        self.daily_loss_limit = 0 # Sẽ được tính toán lại mỗi ngày
        self.consecutive_loss_limit = self.cb_config.get('consecutive_loss_limit', 3)
        self.cooldown_signals_to_skip = self.cb_config.get('consecutive_loss_cooldown_signals', 2)

        # Time Filter / Session Scoring
        self.time_filter_config = trading_params.get('time_filter', {'enabled': False})
        self.use_time_filter = self.time_filter_config.get('enabled', False)
        self.adx_override_threshold = self.time_filter_config.get('adx_override_threshold', 35.0)
        self.sessions = self.time_filter_config.get('sessions', [])
        self.default_multiplier = self.time_filter_config.get('default_multiplier', 1.0)

        # Breakeven Stop
        self.use_breakeven_stop = trading_params.get('use_breakeven_stop', False)
        self.be_trigger = trading_params.get('breakeven_trigger_points', 5.0)
        self.be_extra = trading_params.get('breakeven_extra_points', 1.0)

        # Trailing Stop (Linear)
        self.use_trailing_stop = trading_params.get('use_trailing_stop', False)
        self.trailing_trigger_step = trading_params.get('trailing_trigger_step', 5.0)
        self.trailing_profit_step = trading_params.get('trailing_profit_step', 1.0)
        self.use_atr_based_breakeven = trading_params.get('use_atr_based_breakeven', False)
        self.be_atr_multiplier = trading_params.get('breakeven_atr_trigger_multiplier', 1.0)

        # Tiered Trailing Stop (Advanced)
        self.use_tiered_trailing_stop = trading_params.get('use_tiered_trailing_stop', False)
        self.tiered_trailing_stops = trading_params.get('tiered_trailing_stops', [])
        if self.use_tiered_trailing_stop:
            self.tiered_trailing_stops.sort(key=lambda x: x['trigger'], reverse=True)

        # Multi-Tier Take Profit (Advanced)
        self.multi_tier_tp_config = trading_params.get('multi_tier_tp', {'enabled': False})
 
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
        self.peak_equity = self.initial_balance
        self.equity_curve = [self.initial_balance]
        
        # State for Circuit Breaker
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.current_day = None
        self.cooldown_counter = 0
        self.circuit_breaker_active = False

    def run(self):
        if self.verbose:
            print("Starting backtest...")
        
        # State flag to skip trading after Friday close until Monday
        skip_trading = False

        for i in range(1, len(self.data)):
            current_bar = self.data.iloc[i]
            current_timestamp = current_bar.name
            current_slice = self.data.iloc[:i+1]

            # --- Circuit Breaker: Daily Loss Limit Check ---
            # Reset daily PnL at the start of a new day
            if self.current_day != current_timestamp.date():
                self.current_day = current_timestamp.date()
                self.daily_pnl = 0.0
                # Tính toán lại giới hạn lỗ hàng ngày dựa trên số dư hiện tại
                self.daily_loss_limit = self.balance * (self.daily_loss_limit_percent / 100.0)
                if self.circuit_breaker_active:
                    if self.verbose: print(f"[{current_timestamp}] New day. Resetting daily loss limit circuit breaker.")
                    self.circuit_breaker_active = False

            if self.use_circuit_breaker and self.circuit_breaker_active:
                # If daily loss limit was hit, skip all trading for the rest of the day
                self._check_open_trades(current_slice) # Still need to manage open trades
                continue

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
            
            # --- Circuit Breaker: Consecutive Loss Cooldown ---
            if self.use_circuit_breaker and self.cooldown_counter > 0 and signal != 0:
                if self.verbose: print(f"[{current_timestamp}] Consecutive loss cooldown active. Skipping signal. ({self.cooldown_counter} more to skip)")
                self.cooldown_counter -= 1
                signal = 0 # Ignore the signal

            # --- Time-Based Session Filter ---
            session_multiplier = 1.0
            session_name = "Default"
            if self.use_time_filter and signal != 0:
                current_hour = current_timestamp.hour
                # ADX Override check
                current_adx = current_bar.get('ADX_14_M15', current_bar.get('ADX_14', 0))
                if current_adx > self.adx_override_threshold:
                    session_multiplier = 1.0
                    session_name = f"ADX_Override ({current_adx:.1f})"
                else:
                    found_session = False
                    for session in self.sessions:
                        start, end = session['start_hour'], session['end_hour']
                        # Handle overnight sessions (e.g., 22:00 - 01:00)
                        if start > end:
                            if current_hour >= start or current_hour < end:
                                session_multiplier = session['multiplier']
                                session_name = session['name']
                                found_session = True
                                break
                        elif start <= current_hour < end:
                            session_multiplier = session['multiplier']
                            session_name = session['name']
                            found_session = True
                            break
                    if not found_session:
                        session_multiplier = self.default_multiplier
                        session_name = "Default_Hours"

                # --- NEW: Special logic for 'Avoid' hours ---
                # Only skip if ADX is also low, otherwise just reduce size.
                if "Avoid" in session_name and current_adx < 20:
                     if self.verbose: print(f"[{current_timestamp}] Skipping trade in '{session_name}' due to low ADX ({current_adx:.1f} < 20).")
                     signal = 0 # Skip the trade entirely

                # General skip for any session with multiplier 0 or less
                elif session_multiplier <= 0:
                    signal = 0

            if signal != 0 and len(self.open_trades) < self.max_open_trades:
                self._open_trade(signal, current_bar, dynamic_sl, dynamic_tp, session_multiplier, session_name)

        if self.verbose:
            print("Backtest finished.")
            self.generate_report()

    def _open_trade(self, signal, current_bar, dynamic_sl=None, dynamic_tp=None, session_multiplier=1.0, session_name="Default"):
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
            # --- Drawdown Reducer Logic ---
            current_equity = self.balance
            drawdown_percent = (self.peak_equity - current_equity) / self.peak_equity * 100 if self.peak_equity > 0 else 0
            
            risk_multiplier = 1.0
            for tier in self.drawdown_reducer_tiers:
                if drawdown_percent >= tier['threshold_percent']:
                    risk_multiplier = tier['factor']
                    break # Apply the highest applicable tier

            # --- NEW: Dynamic Risk Amount Calculation based on % Balance ---
            # 1. Calculate target risk amount
            target_risk_amount = self.balance * (self.risk_percent / 100.0) * risk_multiplier * session_multiplier

            # 2. Calculate min and max risk boundaries based on balance
            min_risk_amount = self.balance * (self.min_risk_percent / 100.0)
            max_risk_amount = self.balance * (self.max_risk_percent / 100.0)

            # 3. Clamp the target risk amount within the min/max boundaries
            risk_amount = max(min_risk_amount, min(target_risk_amount, max_risk_amount))
            if self.verbose:
                print(f"Info: Session='{session_name}' (x{session_multiplier}). Risk amount clamped to ${risk_amount:.2f} (Min: ${min_risk_amount:.2f}, Max: ${max_risk_amount:.2f})")
            
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
            'atr_at_entry': current_bar.get('ATRR_14', current_bar.get('ATRR_14_M15')), # Store ATR at entry
            'entry_time': current_bar.name,
            'status': 'open',
            'breakeven_applied': False,
            'tp_extended': False,
            'trailing_steps': 0, # Initialize trailing stop counter
            'sl_reason': 'Initial',
            # --- NEW: Fields for Partial Close ---
            'trade_id': str(uuid.uuid4()), # Unique ID for the trade group
            'original_position_size': position_size,
            'tier': 0, # Initial tier
            'partial_closes': [],
            'peak_profit_runner': 0.0,
            # --- NEW: Logging for new features ---
            'dd_multiplier': risk_multiplier,
            'consecutive_losses_at_entry': self.consecutive_losses,
            'circuit_breaker_active': self.circuit_breaker_active,
            'session_name': session_name,
            'session_multiplier': session_multiplier
        }
        self.open_trades.append(trade)

    def _check_open_trades_old(self, current_slice):
        # This method should only manage existing open trades.
        # It's kept for reference but the new logic is in _check_open_trades
        # Lot size calculation should happen in _open_trade.
        # The previous code block for position_size calculation was misplaced here.
        pass

    def _check_open_trades(self, current_slice):
        current_bar = current_slice.iloc[-1] # Get the latest bar for price checks
        # Thay vì đóng lệnh ngay, chúng ta thu thập thông tin để đóng sau
        # Điều này tránh việc một lệnh bị đóng nhiều lần với các lý do khác nhau trong cùng một tick
        trades_to_process_for_closure = []
        newly_created_trades = []

        # Create a copy to iterate over, as we might modify the list
        for trade in list(self.open_trades):
            # --- Multi-Tier TP Logic ---
            if self.multi_tier_tp_config.get('enabled', False) and trade['status'] == 'open':
                initial_risk_distance = abs(trade['entry_price'] - trade['stop_loss'])
                if initial_risk_distance <= 0: continue

                current_profit_distance = 0
                if trade['type'] == 'BUY':
                    current_profit_distance = current_bar['HIGH'] - trade['entry_price']
                else: # SELL
                    current_profit_distance = trade['entry_price'] - current_bar['LOW']
                
                current_rr = current_profit_distance / initial_risk_distance if initial_risk_distance > 0 else 0

                # Check tiers in order
                tiers = self.multi_tier_tp_config.get('tiers', [])
                next_tier_index = trade.get('tier', 0)

                if next_tier_index < len(tiers):
                    tier_config = tiers[next_tier_index]
                    if current_rr >= tier_config['trigger_rr']:
                        if self.verbose:
                            print(f"[{current_bar.name}] Trade {trade['trade_id']} reached {tier_config['name']} at R:R {current_rr:.2f}. Triggering partial close.")

                        # 1. Calculate size to close
                        size_to_close = trade['original_position_size'] * (tier_config['close_percent'] / 100.0)
                        size_to_close = round(size_to_close / 0.01) * 0.01 # Round to nearest 0.01 lot

                        if size_to_close > 0 and trade['position_size'] > size_to_close:
                            # Create a closed trade record for the partial close
                            partial_close_trade = trade.copy()
                            partial_close_trade['position_size'] = size_to_close
                            
                            exit_price = trade['entry_price'] + (initial_risk_distance * tier_config['trigger_rr']) if trade['type'] == 'BUY' else trade['entry_price'] - (initial_risk_distance * tier_config['trigger_rr'])
                            self._close_trade(partial_close_trade, exit_price, current_bar.name, reason=f"Partial Close {tier_config['name']}")
                            
                            # Update the original (runner) trade
                            trade['position_size'] -= size_to_close
                            trade['partial_closes'].append({'tier': tier_config['name'], 'size': size_to_close, 'price': exit_price})

                        # 2. Update SL/TP for the remaining position
                        if tier_config.get('move_sl_to_breakeven', False):
                            new_sl = trade['entry_price'] + self.be_extra if trade['type'] == 'BUY' else trade['entry_price'] - self.be_extra
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = f"BE after {tier_config['name']}"

                        if 'move_sl_to_rr' in tier_config:
                            sl_rr = tier_config['move_sl_to_rr']
                            new_sl = trade['entry_price'] + (initial_risk_distance * sl_rr) if trade['type'] == 'BUY' else trade['entry_price'] - (initial_risk_distance * sl_rr)
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = f"SL to {sl_rr}R after {tier_config['name']}"

                        if 'new_tp_rr_multiplier' in tier_config:
                            new_tp_distance = initial_risk_distance * tier_config['new_tp_rr_multiplier']
                            trade['take_profit'] = trade['entry_price'] + new_tp_distance if trade['type'] == 'BUY' else trade['entry_price'] - new_tp_distance
                        
                        # Switch to trailing stop mode if configured
                        if 'trailing_stop_atr_multiplier' in tier_config:
                            trade['take_profit'] = 0 # Disable fixed TP
                            trade['trailing_atr_multiplier'] = tier_config['trailing_stop_atr_multiplier']
                            trade['sl_reason'] = f"ATR Trail after {tier_config['name']}"

                        trade['tier'] += 1 # Move to the next tier

            # --- Trailing Stop Logic for Runners ---
            if trade.get('trailing_atr_multiplier', 0) > 0:
                atr = current_bar.get('ATRR_14', 0)
                if atr > 0:
                    atr_sl_distance = atr * trade['trailing_atr_multiplier']
                    if trade['type'] == 'BUY':
                        new_sl = current_bar['HIGH'] - atr_sl_distance
                        if new_sl > trade['stop_loss']:
                            trade['stop_loss'] = new_sl
                    else: # SELL
                        new_sl = current_bar['LOW'] + atr_sl_distance
                        if new_sl < trade['stop_loss']:
                            trade['stop_loss'] = new_sl

            # --- Dynamic Exit Logic ---
            if trade['type'] == 'BUY':
                current_profit = current_bar['HIGH'] - trade['entry_price']
                
                # NOTE: The order of these checks matters. Choose one primary stop-loss management strategy.
                # Tiered Trailing Stop (Advanced)
                if self.use_tiered_trailing_stop and not self.multi_tier_tp_config.get('enabled'):
                    for tier in self.tiered_trailing_stops:
                        if current_profit >= tier['trigger']:
                            new_sl = trade['entry_price'] + tier['sl_add']
                            if new_sl > trade['stop_loss']:
                                trade['stop_loss'] = new_sl
                                trade['sl_reason'] = 'Tiered Trailing'
                            break # Apply highest applicable tier and stop

                # Linear Trailing Stop
                elif self.use_trailing_stop and not self.multi_tier_tp_config.get('enabled', False) and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] + sl_improvement
                        if new_sl > trade['stop_loss']:
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = 'Linear Trailing'
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and not self.multi_tier_tp_config.get('enabled', False):
                    breakeven_trigger_profit = self.be_trigger # Default to fixed points
                    if self.use_atr_based_breakeven and trade.get('atr_at_entry'):
                        breakeven_trigger_profit = trade['atr_at_entry'] * self.be_atr_multiplier

                    if current_profit >= breakeven_trigger_profit:
                        new_sl = trade['entry_price'] + self.be_extra
                        if self.verbose: print(f"[{current_bar.name}] Applying Breakeven for BUY trade. New SL: {new_sl}")
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'Breakeven'
                    trade['breakeven_applied'] = True
                

            else: # SELL
                current_profit = trade['entry_price'] - current_bar['LOW']

                # Tiered Trailing Stop (Advanced)
                if self.use_tiered_trailing_stop and not self.multi_tier_tp_config.get('enabled', False):
                    for tier in self.tiered_trailing_stops:
                        if current_profit >= tier['trigger']:
                            new_sl = trade['entry_price'] - tier['sl_add']
                            if new_sl < trade['stop_loss']:
                                if self.verbose: print(f"[{current_bar.name}] Applying Tiered TS for SELL trade. New SL: {new_sl}")
                                trade['stop_loss'] = new_sl
                                trade['sl_reason'] = 'Tiered Trailing'
                            break

                # Linear Trailing Stop
                elif self.use_trailing_stop and not self.multi_tier_tp_config.get('enabled', False) and self.trailing_trigger_step > 0:
                    profit_steps = math.floor(current_profit / self.trailing_trigger_step)
                    if profit_steps > trade['trailing_steps']:
                        sl_improvement = profit_steps * self.trailing_profit_step
                        new_sl = trade['entry_price'] - sl_improvement
                        if new_sl < trade['stop_loss']:
                            trade['stop_loss'] = new_sl
                            trade['sl_reason'] = 'Linear Trailing'
                        trade['trailing_steps'] = profit_steps

                # Breakeven Stop (Simple)
                elif self.use_breakeven_stop and not trade['breakeven_applied'] and not self.multi_tier_tp_config.get('enabled', False):
                    breakeven_trigger_profit = self.be_trigger # Default to fixed points
                    if self.use_atr_based_breakeven and trade.get('atr_at_entry'):
                        breakeven_trigger_profit = trade['atr_at_entry'] * self.be_atr_multiplier

                    if current_profit >= breakeven_trigger_profit:
                        new_sl = trade['entry_price'] - self.be_extra
                        if self.verbose: print(f"[{current_bar.name}] Applying Breakeven for SELL trade. New SL: {new_sl}")
                        trade['stop_loss'] = new_sl
                        trade['sl_reason'] = 'Breakeven'
                    trade['breakeven_applied'] = True

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
                elif trade['take_profit'] > 0 and current_bar['HIGH'] >= trade['take_profit'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    trades_to_process_for_closure.append((trade, trade['take_profit'], "Take Profit"))
                    continue
            elif trade['type'] == 'SELL':
                if current_bar['HIGH'] >= trade['stop_loss'] and trade not in [t[0] for t in trades_to_process_for_closure]:
                    reason = trade.get('sl_reason', 'Stop Loss')
                    if reason == 'Initial':
                        reason = 'Stop Loss'
                    trades_to_process_for_closure.append((trade, trade['stop_loss'], reason))
                    continue
                elif trade['take_profit'] > 0 and current_bar['LOW'] <= trade['take_profit'] and trade not in [t[0] for t in trades_to_process_for_closure]:
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
        
        # Update balance and equity curve
        self.balance += pnl_currency
        self.equity_curve.append(self.balance)
        self.peak_equity = max(self.peak_equity, self.balance)
        
        # --- Circuit Breaker State Update ---
        if self.use_circuit_breaker:
            self.daily_pnl += pnl_currency
            if pnl_currency > 0:
                # Reset consecutive losses on a win
                self.consecutive_losses = 0
            else: # Loss
                self.consecutive_losses += 1
                # Check for consecutive loss trigger
                if self.consecutive_losses >= self.consecutive_loss_limit:
                    self.cooldown_counter = self.cooldown_signals_to_skip
                    if self.verbose: print(f"[{exit_time}] TRIGGER: {self.consecutive_losses} consecutive losses. Activating cooldown, skipping next {self.cooldown_counter} signals.")
            # Check for daily loss limit trigger
            if self.daily_loss_limit > 0 and self.daily_pnl < -self.daily_loss_limit:
                self.circuit_breaker_active = True
                if self.verbose: print(f"[{exit_time}] TRIGGER: Daily loss limit of ${self.daily_loss_limit} hit (Current Daily PnL: ${self.daily_pnl:.2f}). Halting trading for the day.")

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
