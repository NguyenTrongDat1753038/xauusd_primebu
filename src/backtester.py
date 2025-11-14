import pandas as pd
import numpy as np
from datetime import timedelta

class Backtester:
    """
    Lớp Backtester được thiết kế lại để mô phỏng chính xác hơn các logic
    từ môi trường live trading (run_live.py).

    Bao gồm:
    - Logic vào lệnh chờ nâng cao (Limit & Reverse Entry).
    - Quản lý lệnh đang mở (Breakeven, Tiered Trailing Stop, Reverse TP Extension).
    - Quản lý rủi ro (Time Filter, Circuit Breaker).
    - Mô phỏng hủy lệnh chờ hết hạn.
    """
    def __init__(self, strategy, data, config, verbose=False):
        self.strategy = strategy
        self.data = data
        self.config = config
        self.trading_params = config.get('trading', {})
        self.verbose = verbose

        # Lấy các tham số từ config
        self.initial_balance = self.trading_params.get('initial_balance', 10000)
        self.contract_size = self.trading_params.get('contract_size', 100.0)
        self.min_position_size = self.trading_params.get('min_position_size', 0.01)
        self.max_position_size = self.trading_params.get('max_position_size', 1.0)
        self.volume_step = self.trading_params.get('volume_step', 0.01)

        # Khởi tạo trạng thái backtest
        self.reset_state()

    def reset_state(self):
        """Reset tất cả các biến trạng thái về giá trị ban đầu."""
        self.balance = self.initial_balance
        self.peak_equity = self.initial_balance
        self.equity = self.initial_balance
        self.open_positions = []
        self.pending_orders = []
        self.trade_history = []
        self.last_trade_candle_time = None

        # Trạng thái quản lý rủi ro
        self.daily_pnl = 0.0
        self.current_day = None
        self.consecutive_losses = 0
        self.circuit_breaker_active = False
        self.cooldown_counter = 0

    def _log(self, message):
        """Ghi log nếu chế độ verbose được bật."""
        if self.verbose:
            print(message)

    def _get_session_multiplier(self, timestamp):
        """Mô phỏng logic time_filter từ run_live.py."""
        time_filter_config = self.trading_params.get('time_filter', {})
        if not time_filter_config.get('enabled', False):
            return 1.0, "TimeFilter_Disabled"

        current_hour = timestamp.hour
        for session in time_filter_config.get('sessions', []):
            start, end = session['start_hour'], session['end_hour']
            if (start > end and (current_hour >= start or current_hour < end)) or \
               (start <= current_hour < end):
                return session['multiplier'], session['name']
        
        return time_filter_config.get('default_multiplier', 1.0), "Default_Hours"

    def _calculate_lot_size(self, stop_loss_price, entry_price, session_multiplier):
        """Mô phỏng logic tính toán lot size động từ mt5_connector."""
        if self.balance < self.trading_params.get('balance_threshold_for_fixed_lot', 800):
            return self.trading_params.get('fixed_lot_below_threshold', 0.01)

        risk_percent = self.trading_params.get('risk_percent', 1.0)
        sl_distance = abs(entry_price - stop_loss_price)

        if sl_distance <= 0:
            return 0.0

        # Drawdown Reducer Logic
        risk_multiplier = 1.0
        drawdown_percent = (self.peak_equity - self.equity) / self.peak_equity * 100 if self.peak_equity > 0 else 0
        if drawdown_percent > 0:
            tiers = sorted(self.trading_params.get('drawdown_reducer_tiers', []), key=lambda x: x['threshold_percent'], reverse=True)
            for tier in tiers:
                if drawdown_percent >= tier['threshold_percent']:
                    risk_multiplier = tier['factor']
                    break

        risk_amount = self.balance * (risk_percent / 100.0) * risk_multiplier * session_multiplier
        loss_per_lot = sl_distance * self.contract_size

        if loss_per_lot <= 0:
            return 0.0

        lot_size = risk_amount / loss_per_lot
        
        # Làm tròn và giới hạn
        lot_size = max(self.min_position_size, min(lot_size, self.max_position_size))
        lot_size = round(lot_size / self.volume_step) * self.volume_step
        return lot_size

    def _check_pending_orders(self, candle):
        """Kiểm tra và khớp các lệnh chờ."""
        newly_opened_positions = []
        remaining_pending = []

        for order in self.pending_orders:
            is_triggered = False
            if order['type'] == 'BUY_LIMIT' and candle['LOW'] <= order['entry_price']:
                is_triggered = True
                entry_price = min(candle['OPEN'], order['entry_price']) # Giá khớp thực tế
            elif order['type'] == 'SELL_LIMIT' and candle['HIGH'] >= order['entry_price']:
                is_triggered = True
                entry_price = max(candle['OPEN'], order['entry_price']) # Giá khớp thực tế
            
            if is_triggered:
                self._log(f"--- Lệnh chờ #{order['id']} được khớp tại giá {entry_price:.4f} ---")
                position = {
                    'id': order['id'],
                    'type': 'BUY' if 'BUY' in order['type'] else 'SELL',
                    'entry_price': entry_price,
                    'entry_time': candle.name,
                    'volume': order['volume'],
                    'sl': order['sl'],
                    'tp': order['tp'],
                    'comment': order['comment'],
                    'pnl': 0,
                    'status': 'open'
                }
                newly_opened_positions.append(position)
            else:
                # Hủy lệnh chờ nếu hết hạn
                cancel_hours = self.trading_params.get('cancel_pending_order_hours', 4.0)
                if (candle.name - order['creation_time']) > timedelta(hours=cancel_hours):
                    self._log(f"--- Lệnh chờ #{order['id']} bị hủy do hết hạn ---")
                    # Không cần làm gì thêm, chỉ cần không đưa vào list remaining_pending
                else:
                    remaining_pending.append(order)

        self.pending_orders = remaining_pending
        self.open_positions.extend(newly_opened_positions)

    def _manage_open_positions(self, candle):
        """
        Mô phỏng logic quản lý lệnh từ run_live.py (Breakeven, Trailing, Reverse TP).
        """
        for pos in self.open_positions:
            if pos['status'] != 'open':
                continue

            current_profit = 0
            if pos['type'] == 'BUY':
                current_profit = candle['CLOSE'] - pos['entry_price']
            else: # SELL
                current_profit = pos['entry_price'] - candle['CLOSE']

            # --- Logic đóng lệnh tại SL/TP ---
            if pos['type'] == 'BUY':
                if candle['LOW'] <= pos['sl']:
                    self._close_position(pos, pos['sl'], candle.name, "Stop Loss")
                    continue
                if candle['HIGH'] >= pos['tp']:
                    self._close_position(pos, pos['tp'], candle.name, "Take Profit")
                    continue
            else: # SELL
                if candle['HIGH'] >= pos['sl']:
                    self._close_position(pos, pos['sl'], candle.name, "Stop Loss")
                    continue
                if candle['LOW'] <= pos['tp']:
                    self._close_position(pos, pos['tp'], candle.name, "Take Profit")
                    continue
            
            new_sl = pos['sl']
            new_tp = pos['tp']
            comment_update = pos['comment']

            # --- Logic Reverse Entry TP Extension ---
            reverse_config = self.trading_params.get('reverse_entry_logic', {})
            if reverse_config.get('enabled', False) and 'REV_TP_OLD:' in pos['comment'] and 'REV_TP_EXTENDED' not in pos['comment']:
                try:
                    tp_old_str = pos['comment'].split('REV_TP_OLD:')[1].split('|')[0]
                    tp_old = float(tp_old_str)
                    tp_new_current = pos['tp']
                    distance_to_tp = abs(tp_new_current - pos['entry_price'])
                    
                    min_percent = reverse_config.get('tp_trigger_percent_min', 80.0) / 100.0
                    
                    progress_percent = current_profit / distance_to_tp if distance_to_tp > 0 else 0

                    if progress_percent >= min_percent:
                        self._log(f"--- Kích hoạt Reverse TP Extension cho lệnh #{pos['id']} ---")
                        new_tp = tp_old
                        comment_update = f"{pos['comment']}|REV_TP_EXTENDED"
                except (ValueError, IndexError):
                    pass # Bỏ qua nếu không phân tích được comment

            # --- Logic Tiered Trailing Stop ---
            tiered_ts_config = self.trading_params.get('tiered_trailing_stops', [])
            if self.trading_params.get('use_tiered_trailing_stop', False) and tiered_ts_config:
                sorted_tiers = sorted(tiered_ts_config, key=lambda x: x['trigger'], reverse=True)
                for tier in sorted_tiers:
                    if current_profit >= tier['trigger']:
                        potential_new_sl = pos['entry_price'] + tier['sl_add'] if pos['type'] == 'BUY' else pos['entry_price'] - tier['sl_add']
                        if (pos['type'] == 'BUY' and potential_new_sl > new_sl) or \
                           (pos['type'] == 'SELL' and potential_new_sl < new_sl):
                            new_sl = potential_new_sl
                            comment_update = f"Tiered TS: {tier['trigger']}"
                        break # Chỉ áp dụng bậc cao nhất

            # --- Logic Breakeven ---
            elif self.trading_params.get('use_breakeven_stop', False) and "Breakeven" not in pos['comment']:
                be_trigger = self.trading_params.get('breakeven_trigger_points', 5.0)
                if current_profit >= be_trigger:
                    be_extra = self.trading_params.get('breakeven_extra_points', 0.5)
                    potential_new_sl = pos['entry_price'] + be_extra if pos['type'] == 'BUY' else pos['entry_price'] - be_extra
                    if (pos['type'] == 'BUY' and potential_new_sl > new_sl) or \
                       (pos['type'] == 'SELL' and potential_new_sl < new_sl):
                        new_sl = potential_new_sl
                        comment_update = "Breakeven Applied"

            # Cập nhật nếu có thay đổi
            if new_sl != pos['sl'] or new_tp != pos['tp']:
                self._log(f"--- Cập nhật lệnh #{pos['id']}: SL từ {pos['sl']:.4f} -> {new_sl:.4f}, TP từ {pos['tp']:.4f} -> {new_tp:.4f} ---")
                pos['sl'] = new_sl
                pos['tp'] = new_tp
                pos['comment'] = comment_update

    def _close_position(self, position, close_price, close_time, reason):
        """Đóng một vị thế và ghi lại lịch sử."""
        pnl_points = 0
        if position['type'] == 'BUY':
            pnl_points = close_price - position['entry_price']
        else: # SELL
            pnl_points = position['entry_price'] - close_price

        pnl_currency = pnl_points * position['volume'] * self.contract_size
        
        position['status'] = 'closed'
        position['exit_price'] = close_price
        position['exit_time'] = close_time
        position['pnl_points'] = pnl_points
        position['pnl_currency'] = pnl_currency
        position['reason'] = reason

        self.balance += pnl_currency
        self.equity = self.balance # Cập nhật equity
        self.peak_equity = max(self.peak_equity, self.equity)
        self.daily_pnl += pnl_currency

        self.trade_history.append(position.copy())
        self.open_positions = [p for p in self.open_positions if p['id'] != position['id']]

        self._log(f"--- Đóng lệnh #{position['id']} ({position['type']}) tại {close_price:.4f}. Lý do: {reason}. PnL: ${pnl_currency:.2f} ---")

        # Cập nhật Circuit Breaker
        cb_config = self.trading_params.get('circuit_breaker', {})
        if cb_config.get('enabled', False):
            if pnl_currency < 0:
                self.consecutive_losses += 1
                if self.consecutive_losses >= cb_config.get('consecutive_loss_limit', 3):
                    self.cooldown_counter = cb_config.get('consecutive_loss_cooldown_signals', 2)
                    self._log(f"!!! {self.consecutive_losses} lệnh thua liên tiếp. Kích hoạt cooldown {self.cooldown_counter} lượt.")
            else:
                self.consecutive_losses = 0

    def run(self):
        """Chạy vòng lặp chính của backtest."""
        self.reset_state()
        
        # Sử dụng M15 làm khung thời gian cơ sở để lặp
        base_timeframe_data = self.data

        for i in range(1, len(base_timeframe_data)):
            current_candle = base_timeframe_data.iloc[i]
            current_time = current_candle.name

            # --- 1. Cập nhật trạng thái hàng ngày và Circuit Breaker ---
            if self.current_day != current_time.date():
                self.current_day = current_time.date()
                self.daily_pnl = 0.0
                if self.circuit_breaker_active:
                    self._log(f"--- Ngày mới [{self.current_day}]. Reset Circuit Breaker. ---")
                    self.circuit_breaker_active = False

            cb_config = self.trading_params.get('circuit_breaker', {})
            if cb_config.get('enabled', False):
                daily_loss_limit = self.initial_balance * (cb_config.get('daily_loss_limit_percent', 5.0) / 100.0)
                if self.daily_pnl < -daily_loss_limit:
                    if not self.circuit_breaker_active:
                        self._log(f"!!! CIRCUIT BREAKER KÍCH HOẠT: Lỗ trong ngày (${self.daily_pnl:.2f}) vượt quá giới hạn (-${daily_loss_limit:.2f}).")
                        self.circuit_breaker_active = True
                
                if self.circuit_breaker_active:
                    continue # Bỏ qua nến này

            # --- 2. Quản lý các lệnh đang mở và lệnh chờ ---
            self._check_pending_orders(current_candle)
            self._manage_open_positions(current_candle)

            # --- 3. Tìm tín hiệu mới ---
            # Kiểm tra giới hạn số lệnh
            num_buy = sum(1 for p in self.open_positions if p['type'] == 'BUY') + sum(1 for o in self.pending_orders if 'BUY' in o['type'])
            num_sell = sum(1 for p in self.open_positions if p['type'] == 'SELL') + sum(1 for o in self.pending_orders if 'SELL' in o['type'])
            max_buy = self.trading_params.get('max_buy_orders', 2)
            max_sell = self.trading_params.get('max_sell_orders', 2)

            # Dữ liệu phân tích cho đến nến *trước* nến hiện tại
            analysis_slice = self.data.iloc[:i]
            
            trade_signal, dynamic_sl, dynamic_tp = self.strategy.get_signal(analysis_slice)

            if trade_signal == 0:
                continue

            # --- 4. Xử lý tín hiệu ---
            # Kiểm tra cooldown
            if self.cooldown_counter > 0:
                self._log(f"Tín hiệu bị bỏ qua do cooldown ({self.cooldown_counter} lượt còn lại).")
                self.cooldown_counter -= 1
                continue

            # Kiểm tra giới hạn lệnh
            if trade_signal == 1 and num_buy >= max_buy:
                self._log(f"Tín hiệu BUY bị bỏ qua do đã đạt giới hạn {max_buy} lệnh.")
                continue
            if trade_signal == -1 and num_sell >= max_sell:
                self._log(f"Tín hiệu SELL bị bỏ qua do đã đạt giới hạn {max_sell} lệnh.")
                continue
            
            # Tránh tín hiệu trùng lặp trên cùng một nến
            if self.last_trade_candle_time == analysis_slice.index[-1]:
                continue

            if dynamic_sl is None or dynamic_sl <= 0:
                self._log("Tín hiệu bị bỏ qua do không có SL động.")
                continue

            trade_type = "BUY" if trade_signal == 1 else "SELL"
            self._log(f"*** TÍN HIỆU GỐC {trade_type} TẠI {current_time} ***")

            # --- 5. Áp dụng logic vào lệnh từ run_live.py ---
            use_new_limit_logic = self.trading_params.get('use_new_limit_logic', True)
            
            if use_new_limit_logic:
                current_price = analysis_slice.iloc[-1]['CLOSE'] # Giá đóng cửa của nến tín hiệu
                reverse_config = self.trading_params.get('reverse_entry_logic', {})
                
                final_trade_type = ""
                final_entry_price = 0
                final_sl_price = 0
                final_tp_price = 0
                order_comment = ""

                if reverse_config.get('enabled', False):
                    self._log("--- Áp dụng logic Đảo ngược Entry/SL/TP ---")
                    entry_old, sl_old, tp_old = current_price, dynamic_sl, dynamic_tp
                    
                    entry_new = sl_old
                    tp_new = entry_old
                    sl_distance = abs(sl_old - entry_old)
                    sl_new = sl_old - sl_distance if trade_type == "BUY" else sl_old + sl_distance

                    final_trade_type = "BUY_LIMIT" if trade_type == "BUY" else "SELL_LIMIT"
                    final_entry_price = entry_new
                    final_sl_price = sl_new
                    final_tp_price = tp_new
                    order_comment = f"REV_TP_OLD:{tp_old:.5f}"

                else: # Logic Limit thông thường
                    self._log("--- Áp dụng logic vào lệnh chờ (Limit) ---")
                    original_sl_distance = abs(current_price - dynamic_sl)
                    target_sl_distance = self.trading_params.get('target_sl_distance_points', 6.0)
                    final_sl_distance = max(original_sl_distance, target_sl_distance)

                    final_entry_price = dynamic_sl
                    final_tp_price = current_price # TP ban đầu = giá tín hiệu
                    final_sl_price = final_entry_price - final_sl_distance if trade_type == "BUY" else final_entry_price + final_sl_distance
                    final_trade_type = "BUY_LIMIT" if trade_type == "BUY" else "SELL_LIMIT"
                    order_comment = f"EXT_TP:{dynamic_tp:.5f}" # Lưu TP gốc để tham khảo

                # Tính lot size
                session_multiplier, _ = self._get_session_multiplier(current_time)
                lot_size = self._calculate_lot_size(final_sl_price, final_entry_price, session_multiplier)

                if lot_size > 0:
                    new_order = {
                        'id': len(self.trade_history) + len(self.pending_orders) + 1,
                        'type': final_trade_type,
                        'creation_time': current_time,
                        'entry_price': final_entry_price,
                        'volume': lot_size,
                        'sl': final_sl_price,
                        'tp': final_tp_price,
                        'comment': order_comment,
                        'status': 'pending'
                    }
                    self.pending_orders.append(new_order)
                    self._log(f"--- Đặt lệnh chờ mới: {final_trade_type} | Entry: {final_entry_price:.4f} | SL: {final_sl_price:.4f} | TP: {final_tp_price:.4f} | Lot: {lot_size:.2f} ---")
                    self.last_trade_candle_time = analysis_slice.index[-1]
                else:
                    self._log("Lot size = 0, bỏ qua tín hiệu.")

            else: # Logic vào lệnh thị trường cũ (ít dùng)
                self._log("--- Logic vào lệnh thị trường (Market Order) ---")
                session_multiplier, _ = self._get_session_multiplier(current_time)
                entry_price = current_candle['OPEN'] # Giả lập vào lệnh ở giá mở cửa nến tiếp theo
                lot_size = self._calculate_lot_size(dynamic_sl, entry_price, session_multiplier)

                if lot_size > 0:
                    new_position = {
                        'id': len(self.trade_history) + 1,
                        'type': trade_type,
                        'entry_price': entry_price,
                        'entry_time': current_time,
                        'volume': lot_size,
                        'sl': dynamic_sl,
                        'tp': dynamic_tp,
                        'comment': 'Market Order',
                        'pnl': 0,
                        'status': 'open'
                    }
                    self.open_positions.append(new_position)
                    self._log(f"--- Vào lệnh thị trường: {trade_type} | Entry: {entry_price:.4f} | SL: {dynamic_sl:.4f} | TP: {dynamic_tp:.4f} | Lot: {lot_size:.2f} ---")
                    self.last_trade_candle_time = analysis_slice.index[-1]
                else:
                    self._log("Lot size = 0, bỏ qua tín hiệu.")

        # Đóng tất cả các lệnh còn lại ở cuối backtest
        final_candle = self.data.iloc[-1]
        for pos in self.open_positions:
            if pos['status'] == 'open':
                self._close_position(pos, final_candle['CLOSE'], final_candle.name, "End of Backtest")

        self.print_summary()

    def print_summary(self):
        """In ra báo cáo tóm tắt hiệu suất."""
        print("\n" + "="*20 + " KẾT QUẢ BACKTEST " + "="*20)
        
        total_trades = len(self.trade_history)
        if total_trades == 0:
            print("Không có giao dịch nào được thực hiện.")
            return

        df_results = pd.DataFrame(self.trade_history)
        
        winning_trades = df_results[df_results['pnl_currency'] > 0]
        losing_trades = df_results[df_results['pnl_currency'] <= 0]

        win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = df_results['pnl_currency'].sum()
        profit_factor = abs(winning_trades['pnl_currency'].sum() / losing_trades['pnl_currency'].sum()) if losing_trades['pnl_currency'].sum() != 0 else np.inf
        
        # Tính toán Max Drawdown
        equity_curve = (self.initial_balance + df_results.set_index('exit_time')['pnl_currency'].cumsum()).dropna()
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max
        max_drawdown = drawdown.min()

        print(f"Thời gian Backtest: {self.data.index[0]} -> {self.data.index[-1]}")
        print(f"Số dư ban đầu: ${self.initial_balance:,.2f}")
        print(f"Số dư cuối kỳ: ${self.balance:,.2f}")
        print(f"Tổng lợi nhuận (PnL): ${total_pnl:,.2f} ({(total_pnl/self.initial_balance)*100:.2f}%)")
        print("-" * 40)
        print(f"Tổng số giao dịch: {total_trades}")
        print(f"Tỷ lệ thắng: {win_rate:.2f}%")
        print(f"Lợi nhuận trung bình/thua lỗ trung bình: {abs(winning_trades['pnl_currency'].mean() / losing_trades['pnl_currency'].mean()):.2f}")
        print(f"Hệ số lợi nhuận (Profit Factor): {profit_factor:.2f}")
        print(f"Sụt giảm tối đa (Max Drawdown): {max_drawdown:.2%}")
        print("="*42)

    def save_report_to_csv(self, filename):
        """Lưu lịch sử giao dịch chi tiết ra file CSV."""
        if not self.trade_history:
            print("Không có lịch sử giao dịch để lưu.")
            return
        
        df_report = pd.DataFrame(self.trade_history)
        df_report.to_csv(filename, index=False)
        print(f"Báo cáo chi tiết đã được lưu vào: {filename}")