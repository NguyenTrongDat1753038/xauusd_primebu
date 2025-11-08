import MetaTrader5 as mt5
import time
import datetime
import os
import sys
import setproctitle # Import thư viện setproctitle
import signal

# Thay đổi thư mục làm việc hiện tại thành thư mục gốc của dự án.
# Điều này đảm bảo tất cả các đường dẫn tương đối (ví dụ: tới file config) được giải quyết đúng.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(project_root)
sys.path.insert(0, project_root) # Đảm bảo các module của dự án được ưu tiên import

from src.mt5_connector import connect_to_mt5, get_mt5_data, calculate_dynamic_lot_size, place_order, close_position, cancel_order, _ensure_mt5_connection
from src.analysis import prepare_scalping_data
from src.config_manager import get_config_by_name # Sửa import
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

# Biến toàn cục để kiểm soát vòng lặp chính khi có tín hiệu tắt
shutdown_requested = False
stop_signal_file = None # Khởi tạo biến toàn cục

def shutdown_handler(signum, frame):
    """Xử lý việc tắt bot an toàn."""
    global shutdown_requested
    
    # Đánh dấu để vòng lặp chính biết cần thoát
    shutdown_requested = True
    
    print("\n[!] Đã nhận tín hiệu tắt (Signal: {}). Đang đóng các tiến trình...".format(signum))
    
    try:
        # Đóng tất cả các lệnh đang mở
        positions = mt5.positions_get()
        if positions:
            print(f"Đóng {len(positions)} lệnh đang mở...")
            for pos in positions:
                if pos.magic == 234002:  # magic number của bot
                    close_position(pos, telegram_notifier, "Bot Shutdown")
                    time.sleep(1)
    except:
        print("Lỗi khi đóng các lệnh mở")

    try:
        # Hủy tất cả lệnh chờ
        orders = mt5.orders_get()
        if orders:
            print(f"Hủy {len(orders)} lệnh chờ...")
            for order in orders:
                if order.magic == 234002:  # magic number của bot
                    cancel_order(order.ticket, order.symbol, "PENDING", telegram_notifier)
                    time.sleep(1)
    except:
        print("Lỗi khi hủy lệnh chờ")
    
    # Gửi thông báo Telegram
    if telegram_notifier:
        try:
            msg = "<b>[BOT ĐANG DỪNG]</b>\n"
            msg += "✅ Đã đóng tất cả các lệnh\n"
            msg += "✅ Đã hủy tất cả lệnh chờ\n"
            msg += "⏳ Bot sẽ dừng hoàn toàn trong vài giây..."
            telegram_notifier.send_message(msg)
        except:
            print("Không thể gửi thông báo Telegram khi tắt")
    
    # Đóng kết nối MT5
    try:
        mt5.shutdown()
        print("Đã đóng kết nối MT5")
    except:
        print("Không thể đóng kết nối MT5")
    
    # Set timer để force exit nếu cần
    def force_exit():
        time.sleep(15)  # Đợi 15 giây
        if telegram_notifier:
            try:
                telegram_notifier.send_message("<b>[BOT ĐÃ DỪNG]</b>\n❌ Force shutdown do quá thời gian chờ!")
            except:
                pass
        os._exit(1)
    
    import threading
    threading.Thread(target=force_exit, daemon=True).start()

def graceful_sleep(duration):
    """
    Một hàm sleep có thể bị ngắt bởi tín hiệu shutdown.
    Thay thế cho time.sleep() để bot có thể phản hồi ngay lập tức.
    """
    global shutdown_requested
    end_time = time.time() + duration
    while time.time() < end_time:
        if shutdown_requested:
            break # Thoát khỏi sleep nếu có yêu cầu tắt
        
        # LOGIC MỚI: Kiểm tra file tín hiệu ngay trong lúc sleep
        if os.path.exists(stop_signal_file):
            shutdown_requested = True # Đặt cờ và thoát ngay lập tức
            break
        time.sleep(1) # Ngủ từng giây một để kiểm tra cờ và file

def perform_final_shutdown():
    """Thực hiện các hành động dọn dẹp cuối cùng trước khi thoát."""
    print("\n=== BẮT ĐẦU QUÁ TRÌNH TẮT BOT ===")
    
    # Đóng tất cả các lệnh đang mở nếu được cấu hình
    try:
        positions = mt5.positions_get()
        if positions:
            print(f"Đang đóng {len(positions)} lệnh đang mở...")
            for pos in positions:
                if pos.magic == 234002:  # Chỉ đóng lệnh của bot
                    close_position(pos, telegram_notifier, "Bot Shutdown")
                    time.sleep(1)  # Tránh spam lệnh
    except:
        print("Không thể đóng các lệnh đang mở")
    
    # Hủy tất cả lệnh chờ
    try:
        orders = mt5.orders_get()
        if orders:
            print(f"Đang hủy {len(orders)} lệnh chờ...")
            for order in orders:
                if order.magic == 234002:  # Chỉ hủy lệnh của bot
                    cancel_order(order.ticket, order.symbol, "PENDING", telegram_notifier)
                    time.sleep(1)  # Tránh spam lệnh
    except:
        print("Không thể hủy các lệnh chờ")
    
    # Gửi thông báo cuối cùng và đóng Telegram
    if telegram_notifier:
        try:
            telegram_notifier.send_message("<b>[BOT] Bot đã dừng hoạt động hoàn toàn!</b>")
            # QUAN TRỌNG: KHÔNG gọi shutdown_sync() nữa vì nó gây treo tiến trình.
            # Chúng ta sẽ dựa vào os._exit() để tắt mọi thứ một cách cưỡng chế
            # sau khi đã gửi tin nhắn cuối cùng.
            time.sleep(2) # Đợi 2 giây để đảm bảo tin nhắn được gửi đi.
        except Exception as e: # Sửa lỗi: Bắt lỗi cụ thể hơn nếu cần
            print(f"Không thể gửi thông báo Telegram cuối cùng hoặc tắt notifier: {e}")
    
    # Đóng kết nối MT5
    try:
        mt5.shutdown()
        print("[*] Đã ngắt kết nối khỏi MetaTrader 5")
    except Exception as e: # Sửa lỗi: Bắt lỗi cụ thể hơn
        print(f"Không thể đóng kết nối MT5: {e}")
    
    print("=== KẾT THÚC QUÁ TRÌNH TẮT BOT ===")
    # SỬ DỤNG os._exit(0) ĐỂ BUỘC THOÁT
    # Đây là giải pháp cuối cùng để đảm bảo tiến trình kết thúc hoàn toàn,
    # ngay cả khi các luồng nền của thư viện bên thứ ba (như Telegram) bị treo.
    # Chúng ta đã hoàn thành tất cả các bước dọn dẹp quan trọng ở trên.
    print("[!] Buộc thoát tiến trình để đảm bảo bot dừng hoàn toàn.")
    os._exit(0)

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
        # Lấy magic number từ config để kiểm tra
        magic_number = trading_params.get('magic_number')
        if not magic_number or pos.magic != magic_number:
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
                modify_position_sltp(pos.ticket, final_sl, final_tp, trading_params, notifier, comment_update)

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
        # Magic number đã được lấy từ trading_params trong hàm gọi
        "magic": trading_params.get('magic_number'),
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

def manage_pending_orders(symbol, trading_params, notifier=None):
    """
    Quản lý các lệnh chờ, hủy các lệnh đã tồn tại quá lâu.
    """
    pending_orders = mt5.orders_get(symbol=symbol)
    if pending_orders is None or len(pending_orders) == 0:
        return

    magic_number = trading_params.get('magic_number')
    # Lấy thời gian hủy lệnh từ config, mặc định là 4 giờ
    cancel_after_hours = trading_params.get('cancel_pending_order_hours', 4.0)
    cancel_after_seconds = cancel_after_hours * 3600

    now_utc_ts = datetime.datetime.now(datetime.UTC).timestamp()

    order_type_map = {
        mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT",
        mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
        mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
        mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
    }

    for order in pending_orders:
        # Chỉ kiểm tra các lệnh chờ của bot này
        if order.magic != magic_number:
            continue

        order_age_seconds = now_utc_ts - order.time_setup
        if order_age_seconds > cancel_after_seconds:
            order_type_str = order_type_map.get(order.type, "UNKNOWN_PENDING")
            print(f"--- Lệnh chờ #{order.ticket} ({order_type_str}) đã tồn tại {order_age_seconds/3600:.1f} giờ. Đang tiến hành hủy... ---")
            
            # Gọi hàm hủy lệnh từ mt5_connector
            cancel_order(order.ticket, order.symbol, order_type_str, notifier)
            time.sleep(1) # Chờ một chút sau khi hủy để tránh spam API

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
            
            magic_number = trading_params.get('magic_number')
            
            # --- BƯỚC 1: Đóng tất cả các lệnh đang chạy (positions) ---
            positions = mt5.positions_get(symbol=symbol)
            if positions is None or len(positions) == 0:
                print("Không có lệnh đang chạy nào để đóng.")
            else:
                if notifier:
                    notifier.send_message(f"<b>[ĐÓNG CỬA CUỐI TUẦN]</b>\nĐang đóng {len(positions)} lệnh đang chạy...")
                print(f"Đang đóng {len(positions)} lệnh...")
                for pos in positions:
                    if magic_number and pos.magic == magic_number:
                        close_position(pos, magic_number, notifier, comment="Friday EOD Close")
                        time.sleep(1)
            
            # --- BƯỚC 2: Hủy tất cả các lệnh chờ (pending orders) ---
            pending_orders = mt5.orders_get(symbol=symbol)
            if pending_orders is None or len(pending_orders) == 0:
                print("Không có lệnh chờ nào để hủy.")
            else:
                # Lọc ra các lệnh chờ của bot này
                bot_pending_orders = [order for order in pending_orders if magic_number and order.magic == magic_number]
                if not bot_pending_orders:
                    print("Không có lệnh chờ nào của bot để hủy.")
                else:
                    if notifier:
                        notifier.send_message(f"<b>[ĐÓNG CỬA CUỐI TUẦN]</b>\nĐang hủy {len(bot_pending_orders)} lệnh chờ...")
                    print(f"Đang hủy {len(bot_pending_orders)} lệnh chờ...")
                    order_type_map = { mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT", mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT" }
                    for order in bot_pending_orders:
                        order_type_str = order_type_map.get(order.type, "PENDING")
                        cancel_order(order.ticket, order.symbol, order_type_str, notifier)
                        time.sleep(1) # Tránh spam API

            # --- BƯỚC 3: Đánh dấu đã xử lý và tạm dừng giao dịch ---
            skip_trading_for_weekend = True
            print("Tất cả các lệnh đã được xử lý. Tạm dừng giao dịch cho đến tuần sau.")
            if notifier:
                notifier.send_message("<b>[BOT] Tất cả lệnh đã được đóng. Bot tạm dừng giao dịch cho đến tuần sau.</b>")

def main_trader_loop():
    """Vòng lặp chính để chạy bot."""
    # Khai báo sử dụng các biến toàn cục để có thể đọc và ghi giá trị của chúng
    global shutdown_requested, stop_signal_file

    # Đọc tên config từ tham số dòng lệnh, ví dụ: python run_live.py xauusd_prod
    # --- LOGIC MỚI: Xác định config_name và stop_signal_file ngay từ đầu ---
    if len(sys.argv) < 2:
        print("Lỗi: Vui lòng cung cấp tên cấu hình để chạy.")
        print("Ví dụ: python production/run_live.py xauusd_prod")
        return
    config_name = sys.argv[1]

    # Gán giá trị cho stop_signal_file ngay lập tức để tránh lỗi NameError/TypeError
    stop_signal_file = os.path.join(project_root, f"stop_signal_{config_name}.txt")
    # Kiểm tra và xóa file tín hiệu cũ nếu tồn tại
    if os.path.exists(stop_signal_file):
        print(f"[WARNING] Phát hiện file tín hiệu cũ. Đang xóa: {stop_signal_file}")
        os.remove(stop_signal_file)

    if len(sys.argv) < 2:
        print("Lỗi: Vui lòng cung cấp tên cấu hình để chạy.")
        print("Ví dụ: python production/run_live.py xauusd_prod")
        return
    config_name = sys.argv[1]

    # Đặt tên tiến trình để dễ dàng nhận diện trên Task Manager
    try:
        process_title = f"{config_name}_bot"
        setproctitle.setproctitle(process_title)
        print(f"[*] Đã đặt tên tiến trình thành: {process_title}")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể đặt tên tiến trình: {e}. Đảm bảo thư viện 'setproctitle' đã được cài đặt (pip install setproctitle).")

    config = get_config_by_name(config_name)
    if not config:
        print(f"Không thể tải cấu hình '{config_name}'. Bot sẽ dừng lại.")
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
    # --- LOGIC MỚI: Xác định khung thời gian chính dựa trên chiến lược ---
    if active_strategy_name == 'CprVolumeProfileStrategy':
        strategy = CprVolumeProfileStrategy(strategy_config.get('CprVolumeProfileStrategy', {}))
        prepare_data_func = prepare_scalping_data
        # Nếu là EURGBP swing, dùng H1, ngược lại dùng M5 cho scalping
        main_timeframe_minutes = 60 if 'EURGBP' in trading_params.get('live_symbol') else 5
        required_tfs_for_data = ['m1', 'm5', 'm15', 'h1', 'h4', 'd1']
    elif active_strategy_name == 'M15FilteredScalpingStrategy':
        strategy = M15FilteredScalpingStrategy(strategy_config.get('M15FilteredScalpingStrategy', {}))
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 5 # Chiến lược này luôn chạy trên M5
        required_tfs_for_data = ['m1', 'm5', 'm15', 'h1', 'h4', 'd1']
    else:
        print(f"Lỗi: Chiến thuật '{active_strategy_name}' không được hỗ trợ. Bot sẽ dừng lại.")
        return

    print(f"Đang chạy chiến thuật: {active_strategy_name}")
    
    print(f"Khung thời gian chính để kiểm tra tín hiệu: {main_timeframe_minutes} phút")
    if telegram_config.get('enabled', False):
        try:
            telegram_notifier = TelegramNotifier(telegram_config.get('bot_token'), telegram_config.get('chat_id'))
        except ValueError as e:
            print(f"[LỖI] Không thể khởi tạo Telegram Notifier: {e}")
            telegram_notifier = None
    
    SYMBOL = trading_params.get('live_symbol') # Lấy từ config
    RISK_PERCENT = trading_params.get('risk_percent', 1.0)
    # Sửa lỗi: Lấy max_open_trades và gán cho cả BUY và SELL nếu không có cấu hình riêng
    MAX_OPEN_TRADES = trading_params.get('max_open_trades', 2)
    MAX_BUY_ORDERS = trading_params.get('max_buy_orders', MAX_OPEN_TRADES)
    MAX_SELL_ORDERS = trading_params.get('max_sell_orders', MAX_OPEN_TRADES)
    print("--- Khởi tạo Bot Live Trading ---")
    if account_info:
        print(f"Balance hiện tại: ${account_info.balance:,.2f}")
    print(f"Symbol: {SYMBOL} | Rủi ro mỗi lệnh: {RISK_PERCENT}% | Lệnh tối đa: BUY={MAX_BUY_ORDERS}, SELL={MAX_SELL_ORDERS}")

    # Gửi thông báo khởi động chi tiết qua Telegram
    if telegram_notifier:
        startup_message = (f"<b>[BOT KHỞI ĐỘNG - {SYMBOL}]</b>\n"
                           f"Cấu hình: <code>{config_name}</code>\nChiến thuật: {active_strategy_name}")
        telegram_notifier.send_message(startup_message)

    global skip_trading_for_weekend
    now_on_start = datetime.datetime.now(datetime.UTC)
    
    # --- LOGIC MỚI: Chỉ kiểm tra cuối tuần nếu được bật trong config ---
    # Hợp nhất logic kiểm tra cuối tuần vào một chỗ và tôn trọng cài đặt
    if trading_params.get('close_on_friday', False):
        if now_on_start.weekday() in [5, 6]: # Thứ 7, Chủ Nhật
            skip_trading_for_weekend = True
        elif now_on_start.weekday() == 4: # Thứ 6
            close_time = datetime.datetime.strptime(trading_params.get('friday_close_time', "21:30:00"), '%H:%M:%S').time()
            if now_on_start.time() >= close_time:
                skip_trading_for_weekend = True

    # Đăng ký các trình xử lý tín hiệu để tắt bot một cách an toàn.
    # SIGINT: Ctrl+C trong terminal.
    # SIGTERM: Tín hiệu tắt tiêu chuẩn (ít dùng trên Windows).
    # SIGBREAK: Tín hiệu được gửi bởi `taskkill` (không có /f).
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGBREAK, shutdown_handler)
    print("\n--- Bắt đầu vòng lặp giao dịch ---")
    last_trade_time = None

    while not shutdown_requested:
        try:
            # --- LOGIC MỚI: Kiểm tra file tín hiệu dừng ---
            if os.path.exists(stop_signal_file):
                print(f"\n[!] Phát hiện file tín hiệu dừng '{os.path.basename(stop_signal_file)}'. Bắt đầu quá trình tắt bot...")
                if telegram_notifier:
                    telegram_notifier.send_message("<b>[BOT]</b> Nhận được tín hiệu dừng từ file.")
                # Xóa file tín hiệu để tránh kích hoạt lại
                os.remove(stop_signal_file)
                # Kích hoạt cờ tắt an toàn
                shutdown_requested = True
                continue # Bỏ qua phần còn lại của vòng lặp và đi đến perform_final_shutdown()

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
                graceful_sleep(3600)
                continue

            manage_open_positions(SYMBOL, trading_params, telegram_notifier)
            manage_pending_orders(SYMBOL, trading_params, telegram_notifier) # THÊM BƯỚC QUẢN LÝ LỆNH CHỜ

            cb_config = trading_params.get('circuit_breaker', {})
            if cb_config.get('enabled', False):
                if circuit_breaker_active:
                    print(f"[{now_utc.strftime('%H:%M:%S')}] Đã đạt giới hạn lỗ hàng ngày. Tạm dừng giao dịch.")
                    graceful_sleep(60)
                    continue
                if cooldown_counter > 0:
                    print(f"[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] Đang trong thời gian hồi sau chuỗi thua. Bỏ qua tìm tín hiệu. ({cooldown_counter} lượt)")

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
                graceful_sleep(60); continue

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
                        use_new_limit_logic = trading_params.get('use_new_limit_logic', True)
                        calculated_lot_size = None # Khởi tạo để kiểm tra ở cuối

                        if use_new_limit_logic:
                            print("--- ÁP DỤNG LOGIC VÀO LỆNH CHỜ MỚI ---")
                            current_price = mt5.symbol_info_tick(SYMBOL).ask if trade_type == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
                            if current_price <= 0:
                                print("Không thể lấy giá thị trường hiện tại. Bỏ qua tín hiệu.")
                                continue

                            # 1. Xác định các tham số cho lệnh chờ cuối cùng
                            final_entry_price = dynamic_sl
                            final_tp_price = dynamic_tp
                            
                            original_sl_distance = abs(current_price - dynamic_sl)
                            target_sl_distance = trading_params.get('target_sl_distance_points', 6.0)
                            final_sl_distance = max(original_sl_distance, target_sl_distance)

                            if trade_type == "BUY":
                                final_trade_type = "BUY_LIMIT"
                                final_sl_price = final_entry_price - final_sl_distance
                            else: # SELL
                                final_trade_type = "SELL_LIMIT"
                                final_sl_price = final_entry_price + final_sl_distance

                            print(f"Giá trị gốc: Entry={current_price:.3f}, SL={dynamic_sl:.3f}, TP={dynamic_tp:.3f}")
                            print(f"Tính toán mới: SL Distance gốc={original_sl_distance:.3f}, Target SL Distance={target_sl_distance:.3f} => Chọn SL Distance={final_sl_distance:.3f}")

                            # 2. Tính toán lot size DỰA TRÊN các tham số cuối cùng
                            calculated_lot_size, _ = calculate_dynamic_lot_size(
                                symbol=SYMBOL,
                                stop_loss_price=final_sl_price, # Truyền vào SL cuối cùng
                                trading_params=trading_params,
                                peak_equity=peak_equity,
                                session_multiplier=session_multiplier,
                                entry_price_override=final_entry_price # Truyền giá vào lệnh chờ để tính toán chính xác
                            )

                            if calculated_lot_size and calculated_lot_size > 0:
                                print(f"Lệnh chờ được đặt: {final_trade_type} | Entry: {final_entry_price:.3f} | SL: {final_sl_price:.3f} | TP: {final_tp_price:.3f} | Lot: {calculated_lot_size:.2f}")
                                place_order(SYMBOL, calculated_lot_size, final_trade_type, final_entry_price, final_sl_price, final_tp_price, trading_params.get('magic_number'), telegram_notifier)
                            else:
                                print("Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu.")
                                if telegram_notifier:
                                    telegram_notifier.send_message(f"<b>[BOT] Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu {trade_type}.</b>")
                        else:
                            # Logic đặt lệnh thị trường cũ (nếu use_new_limit_logic = false)
                            print("--- Đặt lệnh thị trường thông thường ---")
                            # SỬA LỖI: Đảm bảo không truyền entry_price_override cho logic cũ
                            calculated_lot_size, final_sl = calculate_dynamic_lot_size(
                                symbol=SYMBOL, stop_loss_price=dynamic_sl, trading_params=trading_params,
                                peak_equity=peak_equity, session_multiplier=session_multiplier
                            )
                            if calculated_lot_size and calculated_lot_size > 0:
                                place_order(SYMBOL, calculated_lot_size, trade_type, 0, final_sl, dynamic_tp, trading_params.get('magic_number'), telegram_notifier)
                            else:
                                print("Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu.")

                        if calculated_lot_size and calculated_lot_size > 0:
                                last_trade_time = current_candle_time # Đánh dấu đã xử lý tín hiệu
                                graceful_sleep(60) # Chờ 1 phút sau khi đặt lệnh để tránh tín hiệu nhiễu
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
            
            graceful_sleep(max(int(sleep_seconds), 5))

        except Exception as e:
            if telegram_notifier:
                telegram_notifier.send_message(f"<b>[LỖI NGHIÊM TRỌNG]</b>\nLỗi trong vòng lặp chính của bot: {e}")
            print(f"Lỗi trong vòng lặp chính: {e}")
            graceful_sleep(60)
    
    # Sau khi vòng lặp kết thúc (do shutdown_requested = True), thực hiện dọn dẹp
    perform_final_shutdown()

if __name__ == "__main__":
    main_trader_loop()