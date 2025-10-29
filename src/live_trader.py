import MetaTrader5 as mt5
import time
import datetime
import os
import sys
import signal

# Import các hàm cần thiết, bao gồm cả hàm sửa và đóng lệnh
from mt5_connector import connect_to_mt5, get_mt5_data, calculate_lot_size, place_order, modify_position_sltp, close_position
from analysis import prepare_analysis_data, prepare_scalping_data # Import cả hai hàm chuẩn bị dữ liệu
from strategies import MultiTimeframeEmaStrategy, ScalpingEmaCrossoverStrategy, SupplyDemandStrategy, PriceActionSRStrategy, MultiEmaPAStochStrategy
from mtf_ema_m1_trigger_strategy import MTF_EMA_M1_Trigger_Strategy # Import chiến lược mới
from combined_strategy import CombinedScalpingStrategy # Import chiến lược kết hợp mới
from m15_filtered_scalping_strategy import M15FilteredScalpingStrategy
from config_manager import get_config
from telegram_notifier import TelegramNotifier

# Biến toàn cục để đảm bảo việc đóng lệnh cuối tuần chỉ chạy 1 lần
# Đổi tên biến để rõ ràng hơn về mục đích của nó: liệu có nên bỏ qua giao dịch không
skip_trading_for_weekend = False # Initial state: not skipping
telegram_notifier = None # Biến toàn cục cho Telegram Notifier

def shutdown_handler(signum, frame):
    """Xử lý việc tắt bot an toàn."""
    print("\n[!] Đã nhận tín hiệu tắt. Đang đóng các tiến trình..." )
    if telegram_notifier:
        telegram_notifier.send_message("<b>[BOT] Bot đang tắt!</b>")
        telegram_notifier.stop() # Dừng luồng Telegram một cách an toàn
    mt5.shutdown()
    print("[*] Đã ngắt kết nối khỏi MetaTrader 5. Tạm biệt!")
    sys.exit(0) # Đảm bảo thoát hoàn toàn

def manage_open_positions(symbol, trading_params, notifier=None):
    """Quản lý các lệnh đang mở, bao gồm dời SL (Breakeven) và Trailing Stop."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None or len(positions) == 0:
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    # Lấy các tham số từ config
    use_breakeven = trading_params.get('use_breakeven_stop', False)
    be_trigger = trading_params.get('breakeven_trigger_points', 10.0)
    be_extra = trading_params.get('breakeven_extra_points', 0.5)

    use_trailing_stop = trading_params.get('use_trailing_stop', False)
    ts_trigger_step = trading_params.get('trailing_trigger_step', 10.0)
    ts_profit_step = trading_params.get('trailing_profit_step', 5.0)

    for pos in positions:
        if pos.magic != 234002: continue

        new_sl = None
        current_profit = 0

        if pos.type == mt5.ORDER_TYPE_BUY:
            current_profit = tick.bid - pos.price_open
            
            # Ưu tiên Trailing Stop nếu được bật
            if use_trailing_stop and ts_trigger_step > 0 and current_profit >= ts_trigger_step:
                # Tính số "bước" lợi nhuận đã đạt được
                profit_steps = int(current_profit // ts_trigger_step)
                # Tính mức SL mới dựa trên số bước
                sl_improvement = profit_steps * ts_profit_step
                potential_new_sl = pos.price_open + sl_improvement
                # Chỉ cập nhật nếu SL mới tốt hơn SL hiện tại
                if potential_new_sl > pos.sl:
                    new_sl = potential_new_sl
            # Nếu không, sử dụng Breakeven
            elif use_breakeven and current_profit >= be_trigger and pos.comment != "Breakeven Applied":
                potential_new_sl = pos.price_open + be_extra
                if potential_new_sl > pos.sl:
                    new_sl = potential_new_sl

        elif pos.type == mt5.ORDER_TYPE_SELL:
            current_profit = pos.price_open - tick.ask

            if use_trailing_stop and ts_trigger_step > 0 and current_profit >= ts_trigger_step:
                profit_steps = int(current_profit // ts_trigger_step)
                sl_improvement = profit_steps * ts_profit_step
                potential_new_sl = pos.price_open - sl_improvement
                if potential_new_sl < pos.sl or pos.sl == 0.0:
                    new_sl = potential_new_sl
            elif use_breakeven and current_profit >= be_trigger and pos.comment != "Breakeven Applied":
                potential_new_sl = pos.price_open - be_extra
                if potential_new_sl < pos.sl or pos.sl == 0.0:
                    new_sl = potential_new_sl

        if new_sl is not None:
            print(f"--- Cập nhật SL cho lệnh #{pos.ticket} --- ")
            modify_position_sltp(pos.ticket, new_sl, pos.tp, notifier)

def handle_friday_close(symbol, trading_params, notifier=None):
    """Kiểm tra và đóng tất cả các lệnh vào cuối tuần."""
    global skip_trading_for_weekend
    now_utc = datetime.datetime.now(datetime.UTC)

    # Reset cờ vào ngày Chủ Nhật hoặc thứ Hai
    # Nếu là Chủ Nhật (6) hoặc Thứ Hai (0), và cờ đang bật, thì tắt cờ
    if now_utc.weekday() in [6, 0]: # Sunday, Monday
        if skip_trading_for_weekend:
            print("[*] Reset cờ bỏ qua giao dịch cuối tuần. Giao dịch có thể tiếp tục.")
            if notifier:
                notifier.send_message("<b>[BOT] Thị trường mở cửa trở lại. Bot tiếp tục giao dịch.</b>")
            skip_trading_for_weekend = False
        return # Không làm gì thêm vào T7, CN, T2

    # Chỉ chạy logic vào thứ Sáu
    if trading_params.get('close_on_friday', False) and now_utc.weekday() == 4: # 4 = Friday
        close_time_str = trading_params.get('friday_close_time', "21:30:00")
        close_time = datetime.datetime.strptime(close_time_str, '%H:%M:%S').time()
        
        # Nếu đã đến giờ đóng cửa và cờ chưa được bật
        # if now_utc.time() >= close_time and not skip_trading_for_weekend: # Original line
        # Nếu đã đến giờ đóng cửa và cờ chưa được bật
        if now_utc.time() >= close_time and not skip_trading_for_weekend:
            print("*** ĐẾN GIỜ ĐÓNG CỬA CUỐI TUẦN ***")
            
            # Lấy tất cả các lệnh đang mở cho symbol hiện tại
            positions = mt5.positions_get(symbol=symbol)
            
            if positions is None or len(positions) == 0:
                print("Không có lệnh nào để đóng.")
            else:
                if notifier:
                    notifier.send_message(f"<b>[THỊ TRƯỜNG ĐÓNG CỬA]</b>\nĐã đến giờ đóng cửa cuối tuần ({close_time_str} UTC). Đang đóng {len(positions)} lệnh...")
                print(f"Đang đóng {len(positions)} lệnh...")
                for pos in positions:
                    # Chỉ đóng các lệnh được mở bởi bot này (dựa trên magic number)
                    if pos.magic == 234002: 
                        close_position(pos, notifier, comment="Friday EOD Close")
                        time.sleep(1) # Thêm độ trễ nhỏ giữa các lệnh đóng
            
            skip_trading_for_weekend = True
            print("Tất cả các lệnh đã được xử lý. Tạm dừng giao dịch cho đến tuần sau.")
            if notifier:
                notifier.send_message("<b>[BOT] Tất cả lệnh đã được đóng. Bot tạm dừng giao dịch cho đến tuần sau.</b>")

def main_trader_loop():
    """Vòng lặp chính để chạy bot."""
    config = get_config()
    if not config:
        print("Không thể tải cấu hình. Bot sẽ dừng lại.")
        return

    # --- Tải cấu hình ---
    trading_params = config.get('trading', {})
    mt5_credentials = config.get('mt5_credentials', {})
    telegram_config = config.get('telegram', {})
    strategy_config = config.get('strategy', {}) # Lấy toàn bộ mục strategy
    
    # --- Khởi tạo các thành phần ---
    if not connect_to_mt5(mt5_credentials.get('login'), mt5_credentials.get('password'), mt5_credentials.get('server')):
        return

    # --- Chọn chiến thuật và hàm chuẩn bị dữ liệu ---
    active_strategy_name = strategy_config.get('active_strategy', 'MultiTimeframeEmaStrategy')
    specific_strategy_params = strategy_config.get(active_strategy_name, {}) # Lấy params của chiến lược đang hoạt động

    if active_strategy_name == 'MultiTimeframeEmaStrategy':
        strategy = MultiTimeframeEmaStrategy(specific_strategy_params)
        prepare_data_func = prepare_analysis_data
        main_timeframe_minutes = 15
        required_tfs_for_data = ['m15', 'm30', 'h1', 'h4']
    elif active_strategy_name == 'ScalpingEmaCrossoverStrategy':
        strategy = ScalpingEmaCrossoverStrategy(specific_strategy_params)
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 5
        required_tfs_for_data = ['m1', 'm5', 'm15']
    elif active_strategy_name == 'SupplyDemandStrategy':
        strategy = SupplyDemandStrategy(specific_strategy_params)
        prepare_data_func = prepare_analysis_data
        main_timeframe_minutes = 15
        required_tfs_for_data = ['m15', 'h4', 'd1']
    elif active_strategy_name == 'CombinedScalpingStrategy':
        strategy = CombinedScalpingStrategy(specific_strategy_params)
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 5
        required_tfs_for_data = ['m1', 'm5', 'm15']
    elif active_strategy_name == 'M15FilteredScalpingStrategy':
        strategy = M15FilteredScalpingStrategy(specific_strategy_params)
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 1 # Vòng lặp chính sẽ chạy nhanh hơn
        required_tfs_for_data = ['m1', 'm5', 'm15']
    elif active_strategy_name == 'MTF_EMA_M1_Trigger_Strategy':
        strategy = MTF_EMA_M1_Trigger_Strategy(specific_strategy_params)
        # Sử dụng dữ liệu scalping vì nó chứa dữ liệu M1 làm cơ sở và các chỉ báo từ khung cao hơn
        prepare_data_func = prepare_scalping_data
        main_timeframe_minutes = 1 # Chạy trên vòng lặp nhanh
        required_tfs_for_data = ['m1', 'm5', 'm15', 'm30', 'h1']
    elif active_strategy_name == 'PriceActionSRStrategy':
        strategy = PriceActionSRStrategy(specific_strategy_params)
        prepare_data_func = prepare_analysis_data
        main_timeframe_minutes = 15
        required_tfs_for_data = ['m15', 'm30', 'h1', 'h4']

    else:
        print(f"Lỗi: Chiến thuật '{active_strategy_name}' không được hỗ trợ. Bot sẽ dừng lại.")
        return
    print(f"Đang chạy chiến thuật: {active_strategy_name}")
    
    # Khởi tạo Telegram Notifier
    global telegram_notifier
    if telegram_config.get('enabled', False):
        try:
            telegram_notifier = TelegramNotifier(telegram_config.get('bot_token'), telegram_config.get('chat_id'))
        except ValueError as e:
            print(f"[LỖI] Không thể khởi tạo Telegram Notifier: {e}")
            telegram_notifier = None
    
    if telegram_notifier:
        telegram_notifier.send_message(f"<b>[BOT] Bot đã khởi động với chiến thuật: {active_strategy_name}!</b>")

    # Lấy các tham số giao dịch từ config
    SYMBOL = trading_params.get('symbol', 'XAUUSD')
    RISK_PERCENT = trading_params.get('risk_percent', 1.0)
    MAX_OPEN_TRADES = trading_params.get('max_open_trades', 1)
    print("--- Khởi tạo Bot Live Trading với cấu hình tối ưu ---")
    print(f"Symbol: {SYMBOL} | Rủi ro mỗi lệnh: {RISK_PERCENT}% | Lệnh tối đa: {MAX_OPEN_TRADES}")
    print(f"Trailing Stop: {'Bật' if trading_params.get('use_trailing_stop') else 'Tắt'} | Trigger: {trading_params.get('trailing_trigger_step')} | Step: {trading_params.get('trailing_profit_step')}")
    print(f"Đóng lệnh cuối tuần: {'Bật' if trading_params.get('close_on_friday') else 'Tắt'} | Giờ đóng: {trading_params.get('friday_close_time')} UTC")

    # Khởi tạo trạng thái skip_trading_for_weekend khi bot bắt đầu
    global skip_trading_for_weekend
    now_on_start = datetime.datetime.now(datetime.UTC)
    if now_on_start.weekday() == 5 or now_on_start.weekday() == 6: # Saturday (5) or Sunday (6)
        skip_trading_for_weekend = True
    elif now_on_start.weekday() == 4: # Friday
        close_time_str = trading_params.get('friday_close_time', "21:30:00")
        close_time = datetime.datetime.strptime(close_time_str, '%H:%M:%S').time()
        if now_on_start.time() >= close_time:
            skip_trading_for_weekend = True

    signal.signal(signal.SIGINT, shutdown_handler)
    print("\n--- Bắt đầu vòng lặp giao dịch ---")
    last_trade_time = None

    while True:
        try:
            handle_friday_close(SYMBOL, trading_params, telegram_notifier) # Cập nhật trạng thái skip_trading_for_weekend
            if skip_trading_for_weekend: # Nếu cờ được bật, bỏ qua tất cả logic giao dịch
                print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Đang trong thời gian nghỉ cuối tuần. Đang chờ đến thứ Hai...")
                time.sleep(3600) # Chờ 1 tiếng rồi kiểm tra lại
                continue

            # --- Quản lý các lệnh đang mở (dời SL) ---
            manage_open_positions(SYMBOL, trading_params, telegram_notifier)

            # --- Logic mở lệnh mới ---
            # Lấy các lệnh đang mở
            # open_positions = mt5.positions_get(symbol=SYMBOL) # Original line
            open_positions = mt5.positions_get(symbol=SYMBOL)
            num_open_trades = len(open_positions) if open_positions else 0
            print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Lệnh đang mở: {num_open_trades}")

            if num_open_trades >= MAX_OPEN_TRADES:
                print(f"Đã đạt giới hạn {MAX_OPEN_TRADES} lệnh. Chờ...")
                time.sleep(60)
                if telegram_notifier:
                    telegram_notifier.send_message(f"<b>[BOT] Đã đạt giới hạn {MAX_OPEN_TRADES} lệnh đang mở. Đang chờ...</b>")
                continue

            print("Đang lấy dữ liệu và tìm tín hiệu...")
            # Lấy dữ liệu cho các khung thời gian cần thiết dựa trên chiến thuật đã chọn
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

            # Chuẩn bị dữ liệu bằng hàm phù hợp với chiến thuật
            # Đối với prepare_analysis_data, cần truyền sr_periods
            if prepare_data_func == prepare_analysis_data:
                analysis_data = prepare_data_func(timeframes_data, specific_strategy_params.get('sr_periods', {}))
            else: # prepare_scalping_data
                analysis_data = prepare_data_func(timeframes_data, strategy_config) # Truyền toàn bộ config của strategy
            
            # Chiến lược giờ đây trả về (tín hiệu, sl, tp)
            trade_signal, dynamic_sl, dynamic_tp = strategy.get_signal(analysis_data)

            if trade_signal != 0:
                current_candle_time = analysis_data.index[-1]
                if last_trade_time == current_candle_time:
                    print(f"Tín hiệu trùng lặp trên nến {current_candle_time}. Bỏ qua.")
                else:
                    trade_type = "BUY" if trade_signal == 1 else "SELL"
                    print(f"*** TÍN HIỆU {trade_type} ĐƯỢC PHÁT HIỆN! ***")
                    
                    # --- Tính toán Lot Size DỰA TRÊN SL ĐỘNG ---
                    if dynamic_sl is not None and dynamic_sl > 0:
                        current_price = mt5.symbol_info_tick(SYMBOL).ask if trade_type == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
                        if current_price > 0:
                            sl_distance_points = abs(current_price - dynamic_sl)
                            print(f"Đang tính toán khối lượng lệnh cho rủi ro {RISK_PERCENT}%...")
                            lot_size = calculate_lot_size(SYMBOL, sl_distance_points, RISK_PERCENT)

                            if lot_size is not None and lot_size > 0:
                                # Truyền giá trị SL/TP cuối cùng vào hàm đặt lệnh
                                place_order(SYMBOL, lot_size, trade_type, dynamic_sl, dynamic_tp, telegram_notifier)
                                last_trade_time = current_candle_time
                                time.sleep(900) # Tạm dừng sau khi đặt lệnh
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
                # if telegram_notifier: telegram_notifier.send_message(f"[{datetime.datetime.now().strftime('%H:%M')}] Không có tín hiệu mới.") # Có thể quá nhiều tin nhắn
            
            # Logic ngủ mới: Nếu là chiến lược scalping, chạy nhanh hơn. Nếu không, chờ nến tiếp theo.
            if "Scalping" in active_strategy_name or "M1_Trigger" in active_strategy_name:
                sleep_seconds = 10 # Quét mỗi 10 giây cho scalping
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