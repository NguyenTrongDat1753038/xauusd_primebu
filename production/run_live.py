import MetaTrader5 as mt5
import time
import datetime
import os
import sys
import signal

# Thay đổi thư mục làm việc hiện tại thành thư mục gốc của dự án.
# Điều này đảm bảo tất cả các đường dẫn tương đối (ví dụ: tới file config) được giải quyết đúng.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(project_root)
sys.path.insert(0, project_root) # Đảm bảo các module của dự án được ưu tiên import

from src.mt5_connector import connect_to_mt5, get_mt5_data, calculate_dynamic_lot_size, place_order, close_position, _ensure_mt5_connection
from src.analysis import prepare_scalping_data
from src.config_manager import get_config_for_env
from src.telegram_notifier import TelegramNotifier
from src.evolution_logger import log_trade_context
from src.cpr_volume_profile_strategy import CprVolumeProfileStrategy
from src.m15_filtered_scalping_strategy import M15FilteredScalpingStrategy

# Import các chiến lược cần thiết

# Biến toàn cục
skip_trading_for_weekend = False
telegram_notifier = None
consecutive_losses = 0
daily_pnl = 0.0
current_day = None
cooldown_counter = 0
circuit_breaker_active = False
peak_equity = 0.0


def shutdown_handler(signum, frame):
    """Xử lý việc tắt bot an toàn."""
    print("\n[!] Đã nhận tín hiệu tắt. Đang đóng các tiến trình..." )
    if telegram_notifier:
        telegram_notifier.send_message("<b>[BOT] Bot đang tắt!</b>")
        telegram_notifier.stop()
    mt5.shutdown()
    print("[*] Đã ngắt kết nối khỏi MetaTrader 5. Tạm biệt!")
    sys.exit(0)

def _get_trade_management_params(trading_params):
    """Helper function to extract all trade management parameters from config."""
    return {
        'use_breakeven': trading_params.get('use_breakeven_stop', False),
        'use_atr_based_breakeven': trading_params.get('use_atr_based_breakeven', False),
        'be_atr_multiplier': trading_params.get('breakeven_atr_trigger_multiplier', 1.0),
        'be_extra': trading_params.get('breakeven_extra_points', 0.5),
        'use_trailing_stop': trading_params.get('use_trailing_stop', False),
        'ts_trigger_step': trading_params.get('trailing_trigger_step', 5.0),
        'ts_profit_step': trading_params.get('trailing_profit_step', 1.0),
        'use_tiered_ts': trading_params.get('use_tiered_trailing_stop', False),
        'tiered_ts_config': sorted(trading_params.get('tiered_trailing_stops', []), key=lambda x: x['trigger'], reverse=True),
        'multi_tier_tp_config': trading_params.get('multi_tier_tp', {'enabled': False}),
    }

def manage_open_positions(symbol, trading_params, notifier=None):
    """
    Quản lý các lệnh đang mở, bao gồm dời SL (Breakeven), Trailing Stop.
    """
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    params = _get_trade_management_params(trading_params)

    for pos in positions:
        if pos.magic != 234002: 
            continue

        new_sl = None
        new_tp = None
        current_profit = 0
        comment_update = None

        if pos.type == mt5.ORDER_TYPE_BUY:
            current_profit = tick.bid - pos.price_open
        elif pos.type == mt5.ORDER_TYPE_SELL:
            current_profit = pos.price_open - tick.ask

        if params['use_tiered_ts'] and not params['multi_tier_tp_config'].get('enabled', False):
            for tier in params['tiered_ts_config']:
                if current_profit >= tier['trigger']:
                    potential_new_sl = pos.price_open + tier['sl_add'] if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - tier['sl_add']
                    if (pos.type == mt5.ORDER_TYPE_BUY and potential_new_sl > pos.sl) or \
                       (pos.type == mt5.ORDER_TYPE_SELL and (potential_new_sl < pos.sl or pos.sl == 0.0)):
                        new_sl = potential_new_sl
                        comment_update = "Tiered Trailing"
                    break

        elif params['use_trailing_stop'] and not params['multi_tier_tp_config'].get('enabled', False) and params['ts_trigger_step'] > 0:
            if current_profit >= params['ts_trigger_step']:
                profit_steps = int(current_profit // params['ts_trigger_step'])
                current_steps = 0
                if "Linear Trailing" in pos.comment:
                    try: current_steps = int(pos.comment.split(":")[-1])
                    except: pass
                if profit_steps > current_steps:
                    sl_improvement = profit_steps * params['ts_profit_step']
                    potential_new_sl = pos.price_open + sl_improvement if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - sl_improvement
                    if (pos.type == mt5.ORDER_TYPE_BUY and potential_new_sl > pos.sl) or \
                       (pos.type == mt5.ORDER_TYPE_SELL and (potential_new_sl < pos.sl or pos.sl == 0.0)):
                        new_sl = potential_new_sl
                        comment_update = f"Linear Trailing:{profit_steps}"

        elif params['use_breakeven'] and not params['multi_tier_tp_config'].get('enabled', False) and "Breakeven" not in pos.comment:
            be_trigger_profit = trading_params.get('breakeven_trigger_points', 5.0)
            if current_profit >= be_trigger_profit:
                potential_new_sl = pos.price_open + params['be_extra']
                if (pos.type == mt5.ORDER_TYPE_BUY and potential_new_sl > pos.sl) or \
                   (pos.type == mt5.ORDER_TYPE_SELL and (potential_new_sl < pos.sl or pos.sl == 0.0)):
                    new_sl = potential_new_sl
                    comment_update = "Breakeven Applied"

        if new_sl is not None or new_tp is not None:
            print(f"--- Cập nhật SL cho lệnh #{pos.ticket} --- ")
            final_sl = new_sl if new_sl is not None else pos.sl
            final_tp = new_tp if new_tp is not None else pos.tp
            if final_sl != pos.sl or final_tp != pos.tp:
                modify_position_sltp(pos.ticket, final_sl, final_tp, notifier, comment_update)

def modify_position_sltp(position_ticket, new_sl, new_tp, notifier=None, comment=None):
    """Sửa đổi SL/TP của một lệnh đang mở."""
    if not _ensure_mt5_connection():
        print("Lỗi: Mất kết nối MT5, không thể sửa lệnh.")
        return False

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_ticket,
        "sl": new_sl,
        "tp": new_tp,
        "magic": 234002,
    }
    if comment:
        request["comment"] = comment
    
    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error_comment = result.comment if result else "mt5.order_send() returned None"
        print(f"Lỗi sửa SL/TP lệnh #{position_ticket}: {error_comment}")
        if notifier: notifier.send_message(f"<b>[LỖI] Sửa SL/TP lệnh #{position_ticket} thất bại!</b>\nLỗi: {error_comment}")
        return False

    print(f"*** Sửa lệnh #{position_ticket} thành công | SL mới: {new_sl:.2f} | TP mới: {new_tp:.2f} | Lý do: {comment} ***")
    if notifier: notifier.send_message(f"<b>[CẬP NHẬT LỆNH] Lệnh #{position_ticket}</b>\nSL mới: {new_sl:.2f}\nTP mới: {new_tp:.2f}\nLý do: {comment}")
    return True

def handle_friday_close(symbol, trading_params, notifier=None):
    """Kiểm tra và đóng tất cả các lệnh vào cuối tuần."""
    global skip_trading_for_weekend
    now_utc = datetime.datetime.now(datetime.UTC)

    if now_utc.weekday() in [6, 0]:
        if skip_trading_for_weekend:
            print("[*] Reset cờ bỏ qua giao dịch cuối tuần. Giao dịch có thể tiếp tục.")
            if notifier:
                notifier.send_message("<b>[BOT] Thị trường mở cửa trở lại. Bot tiếp tục giao dịch.</b>")
            skip_trading_for_weekend = False
        return

    if trading_params.get('close_on_friday', False) and now_utc.weekday() == 4:
        close_time_str = trading_params.get('friday_close_time', "21:30:00")
        close_time = datetime.datetime.strptime(close_time_str, '%H:%M:%S').time()
        
        if now_utc.time() >= close_time and not skip_trading_for_weekend:
            print("*** ĐẾN GIỜ ĐÓNG CỬA CUỐI TUẦN ***")
            
            positions = mt5.positions_get(symbol=symbol)
            
            if positions is None or len(positions) == 0:
                print("Không có lệnh nào để đóng.")
            else:
                if notifier:
                    notifier.send_message(f"<b>[THỊ TRƯỜNG ĐÓNG CỬA]</b>\nĐã đến giờ đóng cửa cuối tuần ({close_time_str} UTC). Đang đóng {len(positions)} lệnh...")
                print(f"Đang đóng {len(positions)} lệnh...")
                for pos in positions:
                    if pos.magic == 234002: 
                        close_position(pos, notifier, comment="Friday EOD Close")
                        time.sleep(1)
            
            skip_trading_for_weekend = True
            print("Tất cả các lệnh đã được xử lý. Tạm dừng giao dịch cho đến tuần sau.")
            if notifier:
                notifier.send_message("<b>[BOT] Tất cả lệnh đã được đóng. Bot tạm dừng giao dịch cho đến tuần sau.</b>")

def main_trader_loop():
    """Vòng lặp chính để chạy bot."""
    config = get_config_for_env('production')
    if not config:
        print("Không thể tải cấu hình. Bot sẽ dừng lại.")
        return

    trading_params = config.get('trading', {})
    mt5_credentials = config.get('mt5_credentials', {})
    telegram_config = config.get('telegram', {})
    strategy_config = config.get('strategy', {})
    
    if not connect_to_mt5(mt5_credentials.get('login'), mt5_credentials.get('password'), mt5_credentials.get('server')):
        return

    global peak_equity, current_day, daily_pnl, circuit_breaker_active, cooldown_counter, telegram_notifier

    account_info = mt5.account_info()
    if account_info:
        peak_equity = account_info.balance
    else:
        print("Không thể lấy thông tin tài khoản ban đầu.")
        peak_equity = trading_params.get('initial_balance', 10000)
    current_day = datetime.datetime.now(datetime.UTC).date()
    daily_pnl = 0.0
    circuit_breaker_active = False

    active_strategy_name = strategy_config.get('active_strategy', 'CprVolumeProfileStrategy')
    if active_strategy_name == 'CprVolumeProfileStrategy':
        strategy = CprVolumeProfileStrategy(strategy_config.get('CprVolumeProfileStrategy', {}))
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 5 # This strategy runs on M5
        required_tfs_for_data = ['m1', 'm5', 'm15', 'h1', 'h4', 'd1']
    elif active_strategy_name == 'M15FilteredScalpingStrategy':
        strategy = M15FilteredScalpingStrategy(strategy_config.get('M15FilteredScalpingStrategy', {}))
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 5 # This strategy also runs on M5
        required_tfs_for_data = ['m1', 'm5', 'm15', 'h1', 'h4', 'd1']
    else:
        print(f"Lỗi: Chiến thuật '{active_strategy_name}' không được hỗ trợ. Bot sẽ dừng lại.")
        return

    print(f"Đang chạy chiến thuật: {active_strategy_name}")
    
    if telegram_config.get('enabled', False):
        try:
            telegram_notifier = TelegramNotifier(telegram_config.get('bot_token'), telegram_config.get('chat_id'))
        except ValueError as e:
            print(f"[LỖI] Không thể khởi tạo Telegram Notifier: {e}")
            telegram_notifier = None
    
    if telegram_notifier:
        telegram_notifier.send_message(f"<b>[BOT] Bot đã khởi động với chiến thuật: {active_strategy_name}!</b>")

    SYMBOL = trading_params.get('live_symbol', 'XAUUSDm')
    RISK_PERCENT = trading_params.get('risk_percent', 1.0)
    # Sửa lỗi: Lấy max_open_trades và gán cho cả BUY và SELL nếu không có cấu hình riêng
    MAX_OPEN_TRADES = trading_params.get('max_open_trades', 2)
    MAX_BUY_ORDERS = trading_params.get('max_buy_orders', MAX_OPEN_TRADES)
    MAX_SELL_ORDERS = trading_params.get('max_sell_orders', MAX_OPEN_TRADES)
    print("--- Khởi tạo Bot Live Trading ---")
    if account_info:
        print(f"Balance hiện tại: ${account_info.balance:,.2f}")
    print(f"Symbol: {SYMBOL} | Rủi ro mỗi lệnh: {RISK_PERCENT}% | Lệnh tối đa: BUY={MAX_BUY_ORDERS}, SELL={MAX_SELL_ORDERS}")

    global skip_trading_for_weekend
    now_on_start = datetime.datetime.now(datetime.UTC)
    if now_on_start.weekday() in [5, 6]:
        skip_trading_for_weekend = True
    elif now_on_start.weekday() == 4:
        close_time_str = trading_params.get('friday_close_time', "21:30:00")
        close_time = datetime.datetime.strptime(close_time_str, '%H:%M:%S').time()
        if now_on_start.time() >= close_time:
            skip_trading_for_weekend = True

    signal.signal(signal.SIGINT, shutdown_handler)
    print("\n--- Bắt đầu vòng lặp giao dịch ---")
    last_trade_time = None

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.UTC)
            if current_day != now_utc.date():
                current_day = now_utc.date()
                daily_pnl = 0.0
                account_info = mt5.account_info()
                if account_info: peak_equity = max(peak_equity, account_info.balance)
                if circuit_breaker_active:
                    print(f"[{now_utc.strftime('%Y-%m-%d')}] Ngày mới. Reset cơ chế ngắt mạch.")
                    circuit_breaker_active = False

            handle_friday_close(SYMBOL, trading_params, telegram_notifier)
            if skip_trading_for_weekend:
                print(f"[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] Đang trong thời gian nghỉ cuối tuần. Chờ đến thứ Hai...")
                time.sleep(3600)
                continue

            manage_open_positions(SYMBOL, trading_params, telegram_notifier)

            cb_config = trading_params.get('circuit_breaker', {})
            if cb_config.get('enabled', False):
                if circuit_breaker_active:
                    print(f"[{now_utc.strftime('%H:%M:%S')}] Đã đạt giới hạn lỗ hàng ngày. Tạm dừng giao dịch.")
                    time.sleep(60)
                    continue
                if cooldown_counter > 0:
                    print(f"[{now_utc.strftime('%H:%M:%S')}] Đang trong thời gian hồi sau chuỗi thua. Bỏ qua tìm tín hiệu. ({cooldown_counter} lượt)")

            # --- LOGIC MỚI: Đếm lệnh BUY và SELL (cả đang chạy và chờ) ---
            num_buy_orders = 0
            num_sell_orders = 0

            # Đếm lệnh đang chạy (positions)
            active_positions = mt5.positions_get(symbol=SYMBOL)
            if active_positions:
                for pos in active_positions:
                    if pos.type == mt5.ORDER_TYPE_BUY:
                        num_buy_orders += 1
                    elif pos.type == mt5.ORDER_TYPE_SELL:
                        num_sell_orders += 1

            # Đếm lệnh chờ (pending orders)
            pending_orders = mt5.orders_get(symbol=SYMBOL)
            if pending_orders:
                for order in pending_orders:
                    if order.type == mt5.ORDER_TYPE_BUY_LIMIT or order.type == mt5.ORDER_TYPE_BUY_STOP:
                        num_buy_orders += 1
                    elif order.type == mt5.ORDER_TYPE_SELL_LIMIT or order.type == mt5.ORDER_TYPE_SELL_STOP:
                        num_sell_orders += 1
            
            print(f"\n[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] Trạng thái lệnh: "
                  f"BUY = {num_buy_orders}/{MAX_BUY_ORDERS}, "
                  f"SELL = {num_sell_orders}/{MAX_SELL_ORDERS}")
            # --- KẾT THÚC LOGIC MỚI ---

            print("Đang lấy dữ liệu và tìm tín hiệu...")
            timeframes_data = {}
            data_loaded_successfully = True
            for tf_name in required_tfs_for_data:
                data = get_mt5_data(SYMBOL, tf_name, 500)
                if data is None:
                    print(f"Lỗi: Không thể lấy dữ liệu cho khung thời gian {tf_name.upper()}.")
                    data_loaded_successfully = False
                    break
                timeframes_data[tf_name.lower()] = data
            
            if not data_loaded_successfully:
                print("Thử lại sau 60 giây.")
                time.sleep(60); continue

            analysis_data = prepare_data_func(timeframes_data, strategy_config)
            
            trade_signal, dynamic_sl, dynamic_tp = strategy.get_signal(analysis_data)

            session_multiplier = 1.0
            session_name = "Default"
            if trade_signal != 0:
                if cb_config.get('enabled', False) and cooldown_counter > 0:
                    print(f"Tín hiệu {trade_signal} bị bỏ qua do cooldown ({cooldown_counter} lượt còn lại).")
                    cooldown_counter -= 1
                    trade_signal = 0

                time_filter_config = trading_params.get('time_filter', {})
                if time_filter_config.get('enabled', True):
                    current_hour = now_utc.hour
                    current_adx = analysis_data.iloc[-1].get('ADX_14_M15', 0)
                    
                    if current_adx > time_filter_config.get('adx_override_threshold', 35.0):
                        session_multiplier = 1.0
                        session_name = f"ADX_Override ({current_adx:.1f})"
                    else:
                        found_session = False
                        for session in time_filter_config.get('sessions', []):
                            start, end = session['start_hour'], session['end_hour']
                            if (start > end and (current_hour >= start or current_hour < end)) or \
                               (start <= current_hour < end):
                                session_multiplier = session['multiplier']
                                session_name = session['name']
                                found_session = True
                                break
                        if not found_session:
                            session_multiplier = time_filter_config.get('default_multiplier', 1.0)
                            session_name = "Default_Hours"

                    if "Avoid" in session_name and current_adx < 20:
                        print(f"Bỏ qua tín hiệu trong phiên '{session_name}' do ADX thấp ({current_adx:.1f} < 20).")
                        trade_signal = 0

            if trade_signal != 0:
                # --- LOGIC MỚI: Kiểm tra giới hạn lệnh trước khi vào lệnh ---
                if trade_signal == 1 and num_buy_orders >= MAX_BUY_ORDERS:
                    print(f"Tín hiệu BUY bị bỏ qua do đã đạt giới hạn {MAX_BUY_ORDERS} lệnh BUY.")
                    trade_signal = 0 # Hủy tín hiệu
                elif trade_signal == -1 and num_sell_orders >= MAX_SELL_ORDERS:
                    print(f"Tín hiệu SELL bị bỏ qua do đã đạt giới hạn {MAX_SELL_ORDERS} lệnh SELL.")
                    trade_signal = 0 # Hủy tín hiệu

            if trade_signal != 0:
                # --- KẾT THÚC LOGIC MỚI ---

                current_candle_time = analysis_data.index[-1]
                if last_trade_time == current_candle_time:
                    print(f"Tín hiệu trùng lặp trên nến {current_candle_time}. Bỏ qua.")
                else:
                    latest_bar_dict = analysis_data.iloc[-1].to_dict()
                    log_trade_context(trade_signal, dynamic_sl, dynamic_tp, latest_bar_dict, session_name, session_multiplier)
                    trade_type = "BUY" if trade_signal == 1 else "SELL"
                    print(f"*** TÍN HIỆU GỐC {trade_type} ĐƯỢC PHÁT HIỆN! ***")
                    
                    if dynamic_sl is not None and dynamic_sl > 0:
                        current_price = mt5.symbol_info_tick(SYMBOL).ask if trade_type == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
                        print(f"Giá vào lệnh gốc dự kiến: {current_price:.2f} | SL gốc: {dynamic_sl:.2f} | TP gốc: {dynamic_tp:.2f}")
                        if current_price > 0:
                            # --- TÍNH TOÁN LOT SIZE DỰA TRÊN RỦI RO GỐC ---
                            calculated_lot_size, final_sl = calculate_dynamic_lot_size(
                                symbol=SYMBOL,
                                stop_loss_price=dynamic_sl,
                                trading_params=trading_params,
                                peak_equity=peak_equity,
                                session_multiplier=session_multiplier
                            )
                            
                            if calculated_lot_size is not None and calculated_lot_size > 0:
                                # --- LOGIC VÀO LỆNH CHỜ (LIMIT ORDER) THEO CÔNG THỨC MỚI ---
                                use_new_limit_logic = trading_params.get('use_new_limit_logic', True) # Thêm cờ mới vào config nếu cần

                                if use_new_limit_logic:
                                    print("--- ÁP DỤNG LOGIC VÀO LỆNH CHỜ MỚI ---")
                                    # Các giá trị gốc từ chiến lược
                                    original_entry_price = current_price # Giá tại thời điểm có tín hiệu
                                    original_sl_price = dynamic_sl      # SL gốc từ chiến lược
                                    original_tp_price = dynamic_tp      # TP gốc từ chiến lược

                                    # 1. Entry mới = SL gốc
                                    new_entry_price = original_sl_price

                                    # 2. Tính toán SL mới
                                    # Khoảng cách SL gốc so với giá vào lệnh gốc
                                    original_sl_distance = abs(original_entry_price - original_sl_price)
                                    # Lấy target_sl_distance_points từ config, mặc định là 6.0
                                    target_sl_distance = trading_params.get('target_sl_distance_points', 6.0)
                                    # Khoảng cách SL mới là giá trị lớn hơn giữa hai khoảng cách trên
                                    new_sl_distance = max(original_sl_distance, target_sl_distance)

                                    # 3. TP mới = TP gốc
                                    new_tp_price = original_tp_price

                                    # 4. Tính toán các giá trị cuối cùng và loại lệnh
                                    if trade_type == "BUY":
                                        new_trade_type = "BUY_LIMIT"
                                        # SL mới được tính từ Entry mới
                                        new_sl_price = new_entry_price - new_sl_distance
                                    else: # SELL
                                        new_trade_type = "SELL_LIMIT"
                                        # SL mới được tính từ Entry mới
                                        new_sl_price = new_entry_price + new_sl_distance
                                    
                                    print(f"Giá trị gốc: Entry={original_entry_price:.2f}, SL={original_sl_price:.2f}, TP={original_tp_price:.2f}")
                                    print(f"Tính toán mới: SL Distance gốc={original_sl_distance:.2f}, Target SL Distance={target_sl_distance:.2f} => Chọn SL Distance={new_sl_distance:.2f}")
                                    print(f"Lệnh chờ được đặt: {new_trade_type} | Entry: {new_entry_price:.2f} | SL: {new_sl_price:.2f} | TP: {new_tp_price:.2f} | Lot: {calculated_lot_size:.2f}")
                                    
                                    # Đặt lệnh LIMIT với các tham số mới, giữ nguyên lot size đã tính
                                    place_order(SYMBOL, calculated_lot_size, new_trade_type, new_entry_price, new_sl_price, new_tp_price, telegram_notifier)

                                else:
                                    print("--- Đặt lệnh thị trường thông thường ---")
                                    # Đặt lệnh thị trường như bình thường
                                    place_order(SYMBOL, calculated_lot_size, trade_type, 0, final_sl, dynamic_tp, telegram_notifier)

                                last_trade_time = current_candle_time # Đánh dấu đã xử lý tín hiệu
                                time.sleep(60) # Chờ 1 phút sau khi đặt lệnh để tránh tín hiệu nhiễu
                            else:
                                print("Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu.")
                                if telegram_notifier:
                                    telegram_notifier.send_message(f"<b>[BOT] Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu {trade_type}.</b>")
                        else:
                            print("Không thể lấy giá thị trường hiện tại. Bỏ qua tín hiệu.")
                    else:
                        print("Chiến lược không trả về SL động. Bỏ qua tín hiệu để đảm bảo an toàn.")
                        if telegram_notifier:
                            telegram_notifier.send_message(f"<b>[CẢNH BÁO] Chiến lược không trả về SL động. Bỏ qua tín hiệu {trade_type}.</b>")
            else:
                print("Không có tín hiệu mới.")
            
            if "Scalping" in active_strategy_name or "M1_Trigger" in active_strategy_name:
                sleep_seconds = 5
                print(f"Chế độ Scalping. Chờ {sleep_seconds} giây...")
            else:
                now = datetime.datetime.now(datetime.UTC)
                next_candle_minute = (now.minute // main_timeframe_minutes + 1) * main_timeframe_minutes
                if next_candle_minute >= 60:
                    next_candle_time = now.replace(hour=now.hour + 1, minute=0, second=5, microsecond=0)
                else:
                    next_candle_time = now.replace(minute=next_candle_minute, second=5, microsecond=0)
                sleep_seconds = (next_candle_time - now).total_seconds()
                print(f"Chờ {sleep_seconds:.0f} giây đến nến tiếp theo (chu kỳ {main_timeframe_minutes} phút)...")
            
            time.sleep(max(int(sleep_seconds), 5))

        except Exception as e:
            if telegram_notifier:
                telegram_notifier.send_message(f"<b>[LỖI NGHIÊM TRỌNG]</b>\nLỗi trong vòng lặp chính của bot: {e}")
            print(f"Lỗi trong vòng lặp chính: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main_trader_loop()