# -*- coding: utf-8 -*-
import MetaTrader5 as mt5
import time
import datetime
import logging
import redis
import json
import os
import sys
import setproctitle # Import thư viện setproctitle
import signal
import requests  # Thêm import requests để gửi HTTP request

# Ensure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Thay đổi thư mục làm việc hiện tại thành thư mục gốc của dự án.
# Điều này đảm bảo tất cả các đường dẫn tương đối (ví dụ: tới file config) được giải quyết đúng.
# SỬA LỖI: Sử dụng os.path.realpath(__file__) để đảm bảo đường dẫn luôn là tuyệt đối,
# tránh lỗi khi chạy script từ một thư mục khác.
project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
os.chdir(project_root)
sys.path.insert(0, project_root) # Đảm bảo các module của dự án được ưu tiên import

from src.mt5_connector import connect_to_mt5, get_mt5_data, calculate_dynamic_lot_size, place_order, close_position, cancel_order, modify_position_sltp
from src.analysis import prepare_scalping_data
from src.config_manager import get_config_by_name # Sửa import
from src.telegram_notifier import TelegramNotifier
from src.evolution_logger import log_trade_context
from src.cpr_volume_profile_strategy import CprVolumeProfileStrategy
from src.m15_filtered_scalping_strategy import M15FilteredScalpingStrategy
from src.eurgbp_swing_strategy import EurgbpSwingStrategy

# --- CẤU HÌNH LOGGING VÀ GIAO TIẾP SERVER ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'  # Ensure UTF-8 encoding for proper Vietnamese character handling
)
logger = logging.getLogger(__name__)

# Server URL và Redis config (nên được truyền qua biến môi trường hoặc tham số)
SERVER_URL = os.environ.get("BOT_MANAGER_SERVER_URL", "http://127.0.0.1:8000")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

redis_client = None
try:
    redis_client = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    redis_client.ping()
    logger.info("Connected to Redis for Pub/Sub.")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Could not connect to Redis: {e}. Real-time updates will be disabled.")
    redis_client = None
# --- KẾT THÚC CẤU HÌNH ---


# Compatibility wrapper: some older/different implementations may have
# differing function signatures. Use this small wrapper to normalize calls
# and avoid crashing the main loop if a TypeError is raised due to
# positional/keyword argument mismatches.
def _safe_modify_position_sltp(*args, **kwargs):
    """
    Robust wrapper around `modify_position_sltp`.
    Accepts either positional or keyword args and maps common positional
    ordering to keyword names. Catches TypeError and other exceptions and
    returns False on failure.
    Expected parameter order (positional):
      position_ticket, new_sl, new_tp, magic_number, comment=None, notifier=None
    """
    try:
        # If caller used keyword args explicitly, prefer that.
        if kwargs:
            return modify_position_sltp(**kwargs)
        # Direct call with positional args
        return modify_position_sltp(*args)
    except TypeError as e:
        # Try to map typical positional call into keywords and retry.
        try:
            mapped = {}
            names = ['position_ticket', 'new_sl', 'new_tp', 'magic_number', 'comment', 'notifier']
            for i, val in enumerate(args):
                if i < len(names):
                    mapped[names[i]] = val
            # Merge with any kwargs passed
            mapped.update(kwargs)
            return modify_position_sltp(**mapped)
        except Exception as e2:
            print(f"[ERROR] modify_position_sltp call failed: {e} | retry error: {e2}")
            return False
    except Exception as e:
        print(f"[ERROR] modify_position_sltp unexpected error: {e}")
        return False

# Import các chiến lược cần thiết

# Biến toàn cục
stop_signal_file = None  # Sẽ được định nghĩa trong main()
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
config_magic_number = 0 # Biến toàn cục để lưu magic number của config hiện tại

def shutdown_handler(signum, frame, notifier=None):
    """Xử lý việc tắt bot an toàn."""
    global shutdown_requested
    
    # Đánh dấu để vòng lặp chính biết cần thoát
    logger.info(f"[!] Đã nhận tín hiệu tắt (Signal: {signum}). Đang đóng các tiến trình...")
    shutdown_requested = True
    
    # Gửi thông báo shutdown đến TradeBot Manager ngay lập tức
    shutdown_message = 'Bot đã nhận tín hiệu dừng và bắt đầu dọn dẹp.'
    try:
        requests.post(f"{SERVER_URL}/api/v1/bots/shutdown_ack", json={
            'bot_id': sys.argv[1] if len(sys.argv) > 1 else 'unknown',
            'reason': f'signal_{signum}',
            'message': shutdown_message
        }, timeout=5)
    except requests.exceptions.RequestException as e:
        logger.warning(f"Không thể gửi thông báo shutdown_ack ngay lập tức: {e}")

    print(shutdown_message)
    if notifier:
        notifier.send_message(f"<b>[BOT SHUTDOWN]</b>\nĐã nhận tín hiệu dừng. Bắt đầu quá trình dọn dẹp.")

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

def perform_final_shutdown(notifier=None, bot_id=None):
    """Thực hiện các hành động dọn dẹp cuối cùng trước khi thoát."""
    print("\n=== BẮT ĐẦU QUÁ TRÌNH TẮT BOT ===")
    
    # Gửi thông báo shutdown đến TradeBot Manager
    if bot_id:
        try:
            shutdown_data = {
                'bot_id': bot_id,
                'reason': 'graceful_shutdown',
                'message': 'Bot đã hoàn tất quá trình dọn dẹp và dừng hoạt động'
            }
            
            # Gửi POST request đến TradeBot Manager (localhost:5000)
            response = requests.post('http://127.0.0.1:5000/api/bot/shutdown', 
                                   json=shutdown_data, 
                                   timeout=5)
            
            if response.status_code == 200:
                print("[*] Đã gửi thông báo shutdown đến TradeBot Manager")
            else:
                print(f"[WARNING] Không thể gửi thông báo shutdown: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Không thể kết nối đến TradeBot Manager để gửi shutdown_ack: {e}")
        except Exception as e:
            logger.warning(f"Lỗi khi gửi thông báo shutdown_ack: {e}")
    
    # Đóng tất cả các lệnh đang mở nếu được cấu hình
    # SỬA LỖI: Sử dụng config_magic_number thay vì số hardcode
    try: # TODO: Cần truyền notifier vào close_position để nó gửi thông báo
        positions = mt5.positions_get()
        if positions:
            logger.info(f"Đang đóng {len(positions)} lệnh đang mở...")
            for pos in positions:
                if pos.magic == config_magic_number:  # Chỉ đóng lệnh của bot này
                    close_position(pos, pos.magic, "Bot Shutdown", notifier=notifier)
                    time.sleep(1)  # Tránh spam lệnh
    except:
        print("Không thể đóng các lệnh đang mở")
    
    # Hủy tất cả lệnh chờ của bot này
    try:
        orders = mt5.orders_get()
        if orders: # TODO: Cần truyền notifier vào cancel_order để nó gửi thông báo
            print(f"Đang hủy {len(orders)} lệnh chờ...")
            for order in orders:
                if order.magic == config_magic_number:  # Chỉ hủy lệnh của bot này
                    cancel_order(order.ticket, order.symbol, "PENDING", notifier=notifier)
                    time.sleep(1)  # Tránh spam lệnh
    except:
        print("Không thể hủy các lệnh chờ")
    
    # Gửi thông báo cuối cùng và đóng Telegram
    if notifier:
        notifier.send_message("<b>[BOT ĐÃ DỪNG]</b>\nBot đã hoàn tất quá trình dọn dẹp và dừng hoạt động.")
        time.sleep(2) # Đợi một chút để đảm bảo thông báo được gửi đi
    
    # Đóng kết nối MT5
    try:
        if mt5.is_connected(): # Chỉ shutdown nếu đang kết nối
            mt5.shutdown()
            logger.info("[*] Đã ngắt kết nối khỏi MetaTrader 5")
    except Exception as e: # Sửa lỗi: Bắt lỗi cụ thể hơn
        logger.error(f"Không thể đóng kết nối MT5: {e}")
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
            current_profit = tick.bid - pos.price_open # Lợi nhuận tính bằng điểm giá
            current_price = tick.bid
        elif pos.type == mt5.ORDER_TYPE_SELL:
            current_profit = pos.price_open - tick.ask # Lợi nhuận tính bằng điểm giá
            current_price = tick.ask

        # --- LOGIC EXIT TỐI ƯU CHO EURGBP SWING STRATEGY ---
        if 'EURGBP' in symbol:
            exit_logic = manage_eurgbp_exit_logic(pos, current_price, current_profit, tick, notifier)
            if exit_logic:
                new_sl = exit_logic.get('new_sl')
                new_tp = exit_logic.get('new_tp')
                comment_update = exit_logic.get('comment')

        # --- LOGIC MỚI: Kiểm tra Reverse Entry Logic - Cập nhật TP khi đạt 80-90% ---
        reverse_config = trading_params.get('reverse_entry_logic', {})
        if reverse_config.get('enabled', False) and 'REV_TP_OLD:' in pos.comment and 'REV_TP_EXTENDED' not in pos.comment:
            try:
                # Trích xuất TP_old từ comment
                tp_old_str = pos.comment.split('REV_TP_OLD:')[1].split('|')[0] if '|' in pos.comment else pos.comment.split('REV_TP_OLD:')[1]
                tp_old = float(tp_old_str)
                
                # TP_new hiện tại (ban đầu = Entry_old)
                tp_new = pos.tp
                
                # Tính khoảng cách từ entry đến TP_new
                distance_to_tp = abs(tp_new - pos.price_open)
                
                # Kiểm tra xem giá hiện tại đã đạt 80-90% TP_new chưa
                min_percent = reverse_config.get('tp_trigger_percent_min', 80.0) / 100.0
                max_percent = reverse_config.get('tp_trigger_percent_max', 90.0) / 100.0
                
                progress_percent = abs(current_price - pos.price_open) / distance_to_tp if distance_to_tp > 0 else 0
                
                if min_percent <= progress_percent <= max_percent:
                    logger.info(f"--- Kích hoạt Reverse TP Extension cho lệnh #{pos.ticket} ---")
                    print(f"Giá hiện tại: {current_price:.3f}, Tiến độ: {progress_percent*100:.1f}%, TP hiện tại: {tp_new:.3f}")
                    print(f"Cập nhật TP từ {tp_new:.3f} sang {tp_old:.3f}")
                    new_tp = tp_old
                    comment_update = f"{pos.comment}|REV_TP_EXTENDED"
            except (ValueError, IndexError) as e:
                print(f"[Lỗi] Không thể phân tích comment Reverse TP cho lệnh #{pos.ticket}: {e}")

        if params['use_tiered_ts'] and not params['multi_tier_tp_config'].get('enabled', False):
            for tier in params['tiered_ts_config']:
                if current_profit >= tier['trigger']:
                    potential_new_sl = pos.price_open + tier['sl_add'] if pos.type == mt5.ORDER_TYPE_BUY else pos.price_open - tier['sl_add']
                    if (pos.type == mt5.ORDER_TYPE_BUY and potential_new_sl > pos.sl) or \
                       (pos.type == mt5.ORDER_TYPE_SELL and (potential_new_sl < pos.sl or pos.sl == 0.0)):
                        new_sl = potential_new_sl
                        comment_update = comment_update if comment_update else "Tiered Trailing"
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
                        comment_update = comment_update if comment_update else f"Linear Trailing:{profit_steps}"

        elif params['use_breakeven'] and not params['multi_tier_tp_config'].get('enabled', False) and "Breakeven" not in pos.comment:
            be_trigger_profit = trading_params.get('breakeven_trigger_points', 5.0)
            if current_profit >= be_trigger_profit:
                potential_new_sl = pos.price_open + params['be_extra']
                if (pos.type == mt5.ORDER_TYPE_BUY and potential_new_sl > pos.sl) or \
                   (pos.type == mt5.ORDER_TYPE_SELL and (potential_new_sl < pos.sl or pos.sl == 0.0)):
                    new_sl = potential_new_sl
                    comment_update = comment_update if comment_update else "Breakeven Applied"

        if new_sl is not None or new_tp is not None:
            logger.info(f"--- Cập nhật SL cho lệnh #{pos.ticket} --- ")
            final_sl = new_sl if new_sl is not None else pos.sl
            final_tp = new_tp if new_tp is not None else pos.tp
            if final_sl != pos.sl or final_tp != pos.tp:
                # Use safe wrapper to avoid runtime TypeError if underlying
                # function signature differs (some environments may import a
                # different version).
                _safe_modify_position_sltp(position_ticket=pos.ticket,
                    new_sl=final_sl,
                    new_tp=final_tp,
                    magic_number=trading_params.get('magic_number'),
                    comment=comment_update,
                    notifier=notifier
                )
                # Publish event (disabled - not implemented)
                # publish_bot_event("position_modified", {
                #     "bot_id": bot_id,
                #     "ticket": pos.ticket,
                #     "new_sl": final_sl,
                #     "new_tp": final_tp,
                #     "comment": comment_update
                # })

def manage_eurgbp_exit_logic(position, current_price, current_profit, tick, notifier=None):
    """
    Logic exit tối ưu cho EURGBP Swing Strategy:
    - Partial close tại TP1 (50% volume)
    - Trailing SL theo EMA34 H1 khi đạt 3R
    - Đóng toàn bộ khi Daily có nến đảo chiều + MACD phân kỳ
    """
    try:
        # Lấy thông tin từ position
        entry_price = position.price_open
        position_type = position.type
        volume = position.volume
        symbol = position.symbol

        # Tính R:R hiện tại
        sl_distance = abs(entry_price - position.sl) if position.sl > 0 else 0
        tp_distance = abs(entry_price - position.tp) if position.tp > 0 else 0
        rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0

        new_sl = None
        new_tp = None
        comment = None
        should_partial_close = False

        # --- 1. BREAKEVEN: Dời SL về BE khi +1R ---
        if current_profit >= sl_distance and "BE_Applied" not in position.comment:
            if position_type == mt5.ORDER_TYPE_BUY:
                new_sl = entry_price + 0.0001  # BE + 1 pip
            else:
                new_sl = entry_price - 0.0001
            comment = "BE_Applied"
            logger.info(f"🔄 Dời SL về BE cho lệnh #{position.ticket} (+{current_profit:.1f} pips)")

        # --- 2. PARTIAL CLOSE: Chốt 50% tại TP1 (2R) ---
        elif current_profit >= 2 * sl_distance and "Partial_Closed" not in position.comment:
            # Tính volume cần đóng (50%)
            close_volume = volume * 0.5

            print(f"💰 Chốt 50% lợi nhuận tại TP1 cho lệnh #{position.ticket}")
            logger.info(f"Đóng {close_volume:.2f} lots, giữ lại {volume - close_volume:.2f} lots")
            
            # Thực hiện partial close
            if position_type == mt5.ORDER_TYPE_BUY:
                close_price = tick.bid
            else:
                close_price = tick.ask

            # Đóng 50% volume
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": close_volume,
                "type": mt5.ORDER_TYPE_SELL if position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": position.ticket,
                "price": close_price,
                "magic": position.magic,
                "comment": "Partial Close TP1"
            })

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Partial close thành công #{position.ticket}")
                if notifier:
                    notifier.send_message(f"💰 <b>PARTIAL CLOSE</b> #{position.ticket}\nChốt 50% tại +{current_profit:.1f} pips")
                
                # Publish event
                publish_bot_event("partial_close", {
                    "bot_id": bot_id, # Cần truyền bot_id vào đây
                    "ticket": position.ticket,
                    "closed_volume": close_volume,
                    "remaining_volume": volume - close_volume,
                    "profit_pips": current_profit
                })
                
                # Dời SL còn lại về +1R
                remaining_sl_distance = sl_distance
                if position_type == mt5.ORDER_TYPE_BUY:
                    new_sl = entry_price + remaining_sl_distance
                else:
                    new_sl = entry_price - remaining_sl_distance
                comment = "Partial_Closed|SL_at_1R"
            else:
                logger.error(f"❌ Partial close thất bại: {result.comment if result else 'Unknown error'}")

        # --- 3. TRAILING SL: Theo EMA34 H1 khi đạt 3R ---
        elif current_profit >= 3 * sl_distance and "EMA_Trailing" not in position.comment:
            # Lấy dữ liệu EMA34 H1
            ema_data = get_mt5_data(symbol, 'h1', 50)
            if ema_data is not None and len(ema_data) > 34:
                # Tính EMA34 (đơn giản)
                ema_period = 34
                prices = ema_data['close'].values
                ema_values = []

                # Tính SMA đầu tiên
                sma = sum(prices[:ema_period]) / ema_period
                ema_values.append(sma)

                # Tính EMA
                multiplier = 2 / (ema_period + 1)
                for i in range(ema_period, len(prices)):
                    ema = (prices[i] - ema_values[-1]) * multiplier + ema_values[-1]
                    ema_values.append(ema)

                current_ema = ema_values[-1] if ema_values else entry_price

                # Trailing theo EMA
                if position_type == mt5.ORDER_TYPE_BUY:
                    # Chỉ trailing nếu giá > EMA và profit > 3R
                    if current_price > current_ema and current_profit > 3 * sl_distance:
                        new_sl = max(position.sl, current_ema - 0.0005) # EMA - 5 pips buffer
                        comment = "EMA_Trailing"
                        logger.info(f"🎯 Trailing SL theo EMA34 H1: {new_sl:.5f}")
                else:
                    if current_price < current_ema and current_profit > 3 * sl_distance:
                        new_sl = min(position.sl, current_ema + 0.0005) # EMA + 5 pips buffer
                        comment = "EMA_Trailing"
                        logger.info(f"🎯 Trailing SL theo EMA34 H1: {new_sl:.5f}")

        # --- 4. EXIT TOÀN BỘ: Khi Daily có nến đảo chiều ---
        # Kiểm tra điều kiện exit toàn bộ (MACD divergence + Daily candle reversal)
        should_exit_all = False

        # Lấy dữ liệu Daily để kiểm tra
        daily_data = get_mt5_data(symbol, 'd1', 10)
        if daily_data is not None and len(daily_data) >= 3:
            # Kiểm tra nến đảo chiều trên Daily
            last_candle = daily_data.iloc[-1]
            prev_candle = daily_data.iloc[-2]

            # Bearish reversal (cho lệnh BUY)
            if position_type == mt5.ORDER_TYPE_BUY:
                bearish_reversal = (last_candle['open'] > last_candle['close'] and  # Nến đỏ
                                   last_candle['high'] > prev_candle['high'] and   # Higher high
                                   last_candle['close'] < prev_candle['close'])    # Lower close
                if bearish_reversal:
                    should_exit_all = True
                    logger.warning(f"🚨 Daily bearish reversal detected - Exit toàn bộ lệnh BUY #{position.ticket}")

            # Bullish reversal (cho lệnh SELL)
            elif position_type == mt5.ORDER_TYPE_SELL:
                bullish_reversal = (last_candle['open'] < last_candle['close'] and  # Nến xanh
                                   last_candle['low'] < prev_candle['low'] and     # Lower low
                                   last_candle['close'] > prev_candle['close'])    # Higher close
                if bullish_reversal:
                    should_exit_all = True
                    logger.warning(f"🚨 Daily bullish reversal detected - Exit toàn bộ lệnh SELL #{position.ticket}")

        if should_exit_all:
            # Đóng toàn bộ lệnh
            close_price = tick.bid if position_type == mt5.ORDER_TYPE_BUY else tick.ask
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": mt5.ORDER_TYPE_SELL if position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                "position": position.ticket,
                "price": close_price,
                "magic": position.magic,
                "comment": "Exit_All_Daily_Reversal"
            })

            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Đóng toàn bộ lệnh #{position.ticket} do Daily reversal")
                if notifier:
                    notifier.send_message(f"🚨 <b>EXIT ALL</b> #{position.ticket}\nDaily reversal detected")
                # Publish event
                publish_bot_event("position_closed", {
                    "bot_id": bot_id, # Cần truyền bot_id vào đây
                    "ticket": position.ticket,
                    "reason": "Daily Reversal",
                    "profit": result.deal.profit # Lấy profit từ deal
                })
            else:
                logger.error(f"❌ Đóng lệnh thất bại: {result.comment if result else 'Unknown error'}")

        return {
            'new_sl': new_sl,
            'new_tp': new_tp,
            'comment': comment,
            'partial_closed': should_partial_close
        } if not should_exit_all else None

    except Exception as e:
        logger.error(f"[Lỗi] EURGBP exit logic cho lệnh #{position.ticket}: {e}")
        return None

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
            order_type_str = order_type_map.get(order.type, "UNKNOWN_PENDING") # TODO: Cần truyền bot_id vào cancel_order
            print(f"--- Lệnh chờ #{order.ticket} ({order_type_str}) đã tồn tại {order_age_seconds/3600:.1f} giờ. Đang tiến hành hủy... ---")
            
            # Gọi hàm hủy lệnh từ mt5_connector
            cancel_order(order.ticket, order.symbol, order_type_str, notifier=notifier)
            time.sleep(1) # Chờ một chút sau khi hủy để tránh spam API

def handle_friday_close(symbol, trading_params, notifier=None):
    """Kiểm tra và đóng tất cả các lệnh vào cuối tuần."""
    global skip_trading_for_weekend
    now_utc = datetime.datetime.now(datetime.UTC)

    if now_utc.weekday() in [6, 0]:
        if skip_trading_for_weekend:
            logger.info("[*] Reset cờ bỏ qua giao dịch cuối tuần. Giao dịch có thể tiếp tục.")
            if notifier:
                notifier.send_message("<b>[BOT] Thị trường mở cửa trở lại. Bot tiếp tục giao dịch.</b>")
            skip_trading_for_weekend = False
        return

    if trading_params.get('close_on_friday', False) and now_utc.weekday() == 4:
        close_time_str = trading_params.get('friday_close_time', "21:30:00")
        close_time = datetime.datetime.strptime(close_time_str, '%H:%M:%S').time()
        
        if now_utc.time() >= close_time and not skip_trading_for_weekend: # TODO: Cần truyền bot_id vào close_position
            logger.warning("*** ĐẾN GIỜ ĐÓNG CỬA CUỐI TUẦN ***")
            
            magic_number = trading_params.get('magic_number')
            
            # --- BƯỚC 1: Đóng tất cả các lệnh đang chạy (positions) ---
            positions = mt5.positions_get(symbol=symbol)
            if positions is None or len(positions) == 0:
                logger.info("Không có lệnh đang chạy nào để đóng.")
            else:
                if notifier:
                    notifier.send_message(f"<b>[ĐÓNG CỬA CUỐI TUẦN]</b>\nĐang đóng {len(positions)} lệnh đang chạy...")
                print(f"Đang đóng {len(positions)} lệnh...")
                for pos in positions:
                    if magic_number and pos.magic == magic_number:
                        close_position(pos, magic_number, "Friday EOD Close", notifier=notifier)
                        time.sleep(1)
            
            # --- BƯỚC 2: Hủy tất cả các lệnh chờ (pending orders) ---
            pending_orders = mt5.orders_get(symbol=symbol)
            if pending_orders is None or len(pending_orders) == 0: # TODO: Cần truyền bot_id vào cancel_order
                logger.info("Không có lệnh chờ nào để hủy.")
            else:
                # Lọc ra các lệnh chờ của bot này
                bot_pending_orders = [order for order in pending_orders if magic_number and order.magic == magic_number]
                if not bot_pending_orders:
                    logger.info("Không có lệnh chờ nào của bot để hủy.")
                else:
                    if notifier:
                        notifier.send_message(f"<b>[ĐÓNG CỬA CUỐI TUẦN]</b>\nĐang hủy {len(bot_pending_orders)} lệnh chờ...")
                    print(f"Đang hủy {len(bot_pending_orders)} lệnh chờ...")
                    order_type_map = { mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT", mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT" }
                    for order in bot_pending_orders:
                        order_type_str = order_type_map.get(order.type, "PENDING")
                        cancel_order(order.ticket, order.symbol, order_type_str, notifier=notifier)
                        time.sleep(1) # Tránh spam API

            # --- BƯỚC 3: Đánh dấu đã xử lý và tạm dừng giao dịch ---
            skip_trading_for_weekend = True
            logger.info("Tất cả các lệnh đã được xử lý. Tạm dừng giao dịch cho đến tuần sau.")
            if notifier:
                notifier.send_message("<b>[BOT] Tất cả lệnh đã được đóng. Bot tạm dừng giao dịch cho đến tuần sau.</b>")

def main_trader_loop():
    """Vòng lặp chính để chạy bot."""
    # Khai báo sử dụng các biến toàn cục để có thể đọc và ghi giá trị của chúng
    global shutdown_requested, skip_trading_for_weekend, telegram_notifier, config_magic_number
    global peak_equity, current_day, daily_pnl, circuit_breaker_active, cooldown_counter, last_heartbeat_time

    # Đọc tên config từ tham số dòng lệnh, ví dụ: python run_live.py xauusd_prod
    # --- LOGIC MỚI: Xác định config_name ngay từ đầu ---
    if len(sys.argv) < 2:
        print("Lỗi: Vui lòng cung cấp tên cấu hình để chạy.")
        print("Ví dụ: python production/run_live.py xauusd_prod")
        return
    config_name = sys.argv[1]

    # Gán giá trị cho stop_signal_file ngay lập tức để tránh lỗi NameError/TypeError
    global stop_signal_file
    stop_signal_file = os.path.join(project_root, f"stop_signal_{config_name}.txt")

    # --- ĐĂNG KÝ PID VỚI SERVER ---
    try:
        response = requests.post(f"{SERVER_URL}/api/v1/bots/register_pid", json={
            "bot_id": config_name,
            "pid": os.getpid(),
            "status": "running"
        })
        response.raise_for_status()
        logger.info(f"Registered PID {os.getpid()} for bot {config_name} with server.")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to register PID with server: {e}. Bot may not be manageable remotely.")
    # --- KẾT THÚC ĐĂNG KÝ PID ---

    # Đặt tên tiến trình để dễ dàng nhận diện trên Task Manager
    try:
        process_title = f"{config_name}_bot"
        setproctitle.setproctitle(process_title)
        logger.info(f"[*] Đã đặt tên tiến trình thành: {process_title}")
        # Publish event (disabled - not implemented)
        # publish_bot_event("bot_started", {"bot_id": config_name, "pid": os.getpid(), "message": "Bot process started."})
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
    
    # Lấy và lưu magic number vào biến toàn cục
    config_magic_number = trading_params.get('magic_number', 0)
    
    if not connect_to_mt5(mt5_credentials.get('login'), mt5_credentials.get('password'), mt5_credentials.get('server')):
        return

    # --- KHỞI TẠO TELEGRAM NOTIFIER ---
    telegram_notifier = None
    if telegram_config.get('enabled', False):
        try:
            telegram_notifier = TelegramNotifier(
                bot_token=telegram_config.get('bot_token'),
                chat_id=telegram_config.get('chat_id')
            )
        except Exception as e:
            print(f"[LỖI] Không thể khởi tạo Telegram Notifier: {e}")

    account_info = mt5.account_info()
    if account_info:
        peak_equity = account_info.balance
    else:
        logger.warning("Không thể lấy thông tin tài khoản ban đầu.")
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
    elif active_strategy_name == 'EurgbpSwingStrategy':
        strategy = EurgbpSwingStrategy(strategy_config.get('EurgbpSwingStrategy', {}))
        prepare_data_func = prepare_scalping_data # Có thể tái sử dụng hàm này
        main_timeframe_minutes = 60 # Chạy trên khung H1
        required_tfs_for_data = ['m1', 'm5', 'm15', 'h1', 'h4', 'd1'] # Cần M1, M5, M15 cho prepare_scalping_data

    else:
        print(f"Lỗi: Chiến thuật '{active_strategy_name}' không được hỗ trợ. Bot sẽ dừng lại.")
        return

    print(f"Đang chạy chiến thuật: {active_strategy_name}")
    logger.info(f"Khung thời gian chính để kiểm tra tín hiệu: {main_timeframe_minutes} phút")
    
    SYMBOL = trading_params.get('live_symbol') # Lấy từ config
    RISK_PERCENT = trading_params.get('risk_percent', 1.0)
    HEARTBEAT_INTERVAL_SECONDS = 60 # Gửi heartbeat mỗi 60 giây
    last_heartbeat_time = time.time()
    # Sửa lỗi: Lấy max_open_trades và gán cho cả BUY và SELL nếu không có cấu hình riêng
    MAX_OPEN_TRADES = trading_params.get('max_open_trades', 2)
    MAX_BUY_ORDERS = trading_params.get('max_buy_orders', MAX_OPEN_TRADES)
    MAX_SELL_ORDERS = trading_params.get('max_sell_orders', MAX_OPEN_TRADES)
    TRADE_COOLDOWN_SECONDS = trading_params.get('trade_cooldown_seconds', 300) # Lấy từ config, mặc định 5 phút
    print("--- Khởi tạo Bot Live Trading ---")
    if account_info:
        logger.info(f"Balance hiện tại: ${account_info.balance:,.2f}")
    print(f"Symbol: {SYMBOL} | Rủi ro mỗi lệnh: {RISK_PERCENT}% | Lệnh tối đa: BUY={MAX_BUY_ORDERS}, SELL={MAX_SELL_ORDERS}")



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
    signal.signal(signal.SIGINT, lambda s, f: shutdown_handler(s, f, telegram_notifier))
    signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler(s, f, telegram_notifier)) # TODO: Cần truyền bot_id vào shutdown_handler
    signal.signal(signal.SIGBREAK, lambda s, f: shutdown_handler(s, f, telegram_notifier))
    logger.info("\n--- Bắt đầu vòng lặp giao dịch ---")
    if telegram_notifier:
        telegram_notifier.send_message(f"🚀 <b>BOT KHỞI ĐỘNG</b>\nCấu hình: {config_name}\nChiến lược: {active_strategy_name}\nSymbol: {SYMBOL}")
    last_trade_time = None

    while not shutdown_requested:
        try:
            # --- GỬI HEARTBEAT ĐỊNH KỲ ---
            if time.time() - last_heartbeat_time > HEARTBEAT_INTERVAL_SECONDS:
                try:
                    requests.post(f"{SERVER_URL}/api/v1/bots/heartbeat", json={"bot_id": config_name}, timeout=5)
                    last_heartbeat_time = time.time()
                    # logger.debug(f"Heartbeat sent for {config_name}")
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Failed to send heartbeat to server for {config_name}: {e}")
            # --- KẾT THÚC HEARTBEAT ---

            # --- LOGIC CŨ: Kiểm tra file tín hiệu dừng (ĐÃ BỎ) ---
            # if os.path.exists(stop_signal_file): ...
            # --- KẾT THÚC LOGIC CŨ ---

            now_utc = datetime.datetime.now(datetime.UTC)
            if current_day != now_utc.date():
                current_day = now_utc.date()
                daily_pnl = 0.0
                account_info = mt5.account_info()
                if account_info: peak_equity = max(peak_equity, account_info.balance)
                if circuit_breaker_active:
                    print(f"[{now_utc.strftime('%Y-%m-%d')}] Ngày mới. Reset cơ chế ngắt mạch.")
                    circuit_breaker_active = False # TODO: Cần publish event khi trạng thái CB thay đổi

            handle_friday_close(SYMBOL, trading_params, telegram_notifier)
            if skip_trading_for_weekend:
                logger.info(f"[{now_utc.strftime('%Y-%m-%d %H:%M:%S')}] Đang trong thời gian nghỉ cuối tuần. Chờ đến thứ Hai...")
                graceful_sleep(3600)
                continue

            manage_open_positions(SYMBOL, trading_params, telegram_notifier)
            manage_pending_orders(SYMBOL, trading_params, telegram_notifier) # THÊM BƯỚC QUẢN LÝ LỆNH CHỜ

            cb_config = trading_params.get('circuit_breaker', {})
            if cb_config.get('enabled', False): # TODO: Cần publish event khi trạng thái CB thay đổi
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
            # --- KẾT THÚC LOGIC ĐẾM LỆNH ---

            logger.info("Đang lấy dữ liệu và tìm tín hiệu...")
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
                if cb_config.get('enabled', False) and cooldown_counter > 0: # TODO: Cần publish event khi tín hiệu bị bỏ qua
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
                        logger.info(f"Bỏ qua tín hiệu trong phiên '{session_name}' do ADX thấp ({current_adx:.1f} < 20).")
                        trade_signal = 0

            if trade_signal != 0:
                # --- LOGIC MỚI: Kiểm tra giới hạn lệnh trước khi vào lệnh ---
                if trade_signal == 1 and num_buy_orders >= MAX_BUY_ORDERS:
                    logger.info(f"Tín hiệu BUY bị bỏ qua do đã đạt giới hạn {MAX_BUY_ORDERS} lệnh BUY.")
                    trade_signal = 0 # Hủy tín hiệu
                elif trade_signal == -1 and num_sell_orders >= MAX_SELL_ORDERS:
                    logger.info(f"Tín hiệu SELL bị bỏ qua do đã đạt giới hạn {MAX_SELL_ORDERS} lệnh SELL.")
                    trade_signal = 0 # Hủy tín hiệu

            if trade_signal != 0:
                # --- KẾT THÚC LOGIC MỚI ---

                current_candle_time = analysis_data.index[-1]
                if last_trade_time == current_candle_time:
                    print(f"Tín hiệu trùng lặp trên nến {current_candle_time}. Bỏ qua.")
                else:
                    latest_bar_dict = analysis_data.iloc[-1].to_dict()
                    log_trade_context(trade_signal, dynamic_sl, dynamic_tp, latest_bar_dict, session_name, session_multiplier)
                    trade_type = "BUY" if trade_signal == 1 else "SELL" # TODO: Cần truyền bot_id vào place_order
                    logger.info(f"*** TÍN HIỆU GỐC {trade_type} ĐƯỢC PHÁT HIỆN! ***")
                    
                    if dynamic_sl is not None and dynamic_sl > 0:
                        use_new_limit_logic = trading_params.get('use_new_limit_logic', True)
                        calculated_lot_size = None # Khởi tạo để kiểm tra ở cuối # TODO: Cần publish event khi lệnh được đặt

                        if use_new_limit_logic:
                            print("--- ÁP DỤNG LOGIC VÀO LỆNH CHỜ MỚI ---")
                            current_price = mt5.symbol_info_tick(SYMBOL).ask if trade_type == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
                            if current_price <= 0:
                                print("Không thể lấy giá thị trường hiện tại. Bỏ qua tín hiệu.")
                                continue

                            # --- LOGIC ĐẢO NGƯỢC ENTRY/SL/TP ---
                            reverse_config = trading_params.get('reverse_entry_logic', {})
                            reverse_enabled = reverse_config.get('enabled', False)

                            if reverse_enabled:
                                print("--- ÁP DỤNG LOGIC ĐẢO NGƯỢC ENTRY/SL/TP ---")
                                # Tính toán từ chiến lược gốc
                                entry_old = current_price
                                sl_old = dynamic_sl
                                tp_old = dynamic_tp

                                # Đảo ngược để tạo lệnh mới
                                entry_new = sl_old
                                tp_new = entry_old  # TP ban đầu = Entry cũ
                                
                                # Tính SL mới dựa trên khoảng cách
                                sl_distance = abs(sl_old - entry_old)
                                
                                if trade_type == "BUY":
                                    # BUY: SL_new = SL_old - abs(SL_old - Entry_old)
                                    sl_new = sl_old - sl_distance
                                    final_trade_type = "BUY_LIMIT"
                                else:  # SELL
                                    # SELL: SL_new = SL_old + abs(SL_old - Entry_old)
                                    sl_new = sl_old + sl_distance
                                    final_trade_type = "SELL_LIMIT"

                                final_entry_price = entry_new
                                final_sl_price = sl_new
                                final_tp_price = tp_new
                                
                                print(f"Giá trị gốc: Entry_old={entry_old:.3f}, SL_old={sl_old:.3f}, TP_old={tp_old:.3f}")
                                print(f"Giá trị đảo ngược: Entry_new={entry_new:.3f}, SL_new={sl_new:.3f}, TP_new={tp_new:.3f}")
                                print(f"TP_old sẽ được áp dụng khi giá đạt 80-90% TP_new (khoảng {tp_new * 0.85:.3f})")
                            else:
                                # Logic cũ (không đảo ngược)
                                # Entry_old chính là current_price (giá khi tín hiệu được tạo)
                                # TP_old chính là dynamic_tp (TP do chiến lược tính toán)
                                initial_tp_price = current_price # TP_new = Entry_old
                                extended_tp_price = dynamic_tp  # TP sẽ được mở rộng tới

                                # 1. Xác định các tham số cho lệnh chờ cuối cùng
                                final_entry_price = dynamic_sl
                                final_tp_price = initial_tp_price # Đặt TP ban đầu
                                
                                # Entry_old là current_price, SL_old là dynamic_sl
                                original_sl_distance = abs(current_price - dynamic_sl) 
                                target_sl_distance = trading_params.get('target_sl_distance_points', 6.0)
                                final_sl_distance = max(original_sl_distance, target_sl_distance)

                                if trade_type == "BUY":
                                    final_trade_type = "BUY_LIMIT"
                                    final_sl_price = final_entry_price - final_sl_distance
                                else: # SELL
                                    final_trade_type = "SELL_LIMIT"
                                    final_sl_price = final_entry_price + final_sl_distance

                                logger.info(f"Giá trị gốc: Entry={current_price:.3f}, SL={dynamic_sl:.3f}, TP={dynamic_tp:.3f}")
                                logger.info(f"Tính toán mới: SL Distance gốc={original_sl_distance:.3f}, Target SL Distance={target_sl_distance:.3f} => Chọn SL Distance={final_sl_distance:.3f}")

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
                                # Chuẩn bị comment để lưu TP_old
                                order_comment = ""
                                
                                if reverse_enabled:
                                    # Lưu TP_old để sau này modify
                                    order_comment = f"REV_TP_OLD:{tp_old:.3f}"
                                
                                logger.info(f"Lệnh chờ được đặt: {final_trade_type} | Entry: {final_entry_price:.3f} | SL: {final_sl_price:.3f} | TP: {final_tp_price:.3f} | Lot: {calculated_lot_size:.2f}")
                                place_order(SYMBOL, calculated_lot_size, final_trade_type, final_entry_price, final_sl_price, final_tp_price, trading_params.get('magic_number'), telegram_notifier, comment=order_comment)
                            else:
                                logger.warning("Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu.")

                        else:
                            # Logic đặt lệnh thị trường cũ (nếu use_new_limit_logic = false)
                            logger.info("--- Đặt lệnh thị trường thông thường ---")
                            # SỬA LỖI: Đảm bảo không truyền entry_price_override cho logic cũ
                            calculated_lot_size, final_sl = calculate_dynamic_lot_size(
                                symbol=SYMBOL, stop_loss_price=dynamic_sl, trading_params=trading_params,
                                peak_equity=peak_equity, session_multiplier=session_multiplier
                            )
                            if calculated_lot_size and calculated_lot_size > 0:
                                place_order(SYMBOL, calculated_lot_size, trade_type, 0, final_sl, dynamic_tp, trading_params.get('magic_number'), telegram_notifier, comment="PyBot Market Order") # TODO: Cần publish event khi lệnh được đặt
                            else:
                                logger.warning("Không thể tính toán khối lượng lệnh hoặc khối lượng bằng 0. Bỏ qua tín hiệu.")

                        if calculated_lot_size and calculated_lot_size > 0:
                                # Publish event for new order (disabled - not implemented)
                                # publish_bot_event("order_placed", {
                                #     "bot_id": config_name,
                                #     "symbol": SYMBOL,
                                #     "type": trade_type,
                                #     "volume": calculated_lot_size,
                                #     "sl": final_sl,
                                #     "tp": dynamic_tp
                                # })
                                last_trade_time = current_candle_time # Đánh dấu đã xử lý tín hiệu
                                print(f"--- Lệnh đã được đặt. Bắt đầu thời gian chờ {TRADE_COOLDOWN_SECONDS} giây. ---")
                                graceful_sleep(TRADE_COOLDOWN_SECONDS) # Chờ sau khi đặt lệnh để tránh tín hiệu nhiễu
                    else:
                        print("Chiến lược không trả về SL động. Bỏ qua tín hiệu để đảm bảo an toàn.")

            else:
                logger.debug("Không có tín hiệu mới.")
            
            if "Scalping" in active_strategy_name or "M1_Trigger" in active_strategy_name:
                sleep_seconds = 5
                print(f"Chế độ Scalping. Chờ {sleep_seconds} giây...")
            else:
                now = datetime.datetime.now(datetime.UTC)
                next_candle_minute = (now.minute // main_timeframe_minutes + 1) * main_timeframe_minutes
                if next_candle_minute >= 60:
                    # Use timedelta to properly handle hour overflow (23:xx -> 00:xx next day)
                    next_candle_time = now.replace(minute=0, second=5, microsecond=0) + datetime.timedelta(hours=1)
                else:
                    next_candle_time = now.replace(minute=next_candle_minute, second=5, microsecond=0)
                sleep_seconds = (next_candle_time - now).total_seconds()
                print(f"Chờ {sleep_seconds:.0f} giây đến nến tiếp theo (chu kỳ {main_timeframe_minutes} phút)...")
            
            graceful_sleep(max(int(sleep_seconds), 5))

        except Exception as e:
            logger.error(f"Lỗi trong vòng lặp chính: {e}", exc_info=True) # exc_info=True để in stack trace
            if telegram_notifier:
                telegram_notifier.send_message(f"<b>[LỖI NGHIÊM TRỌNG]</b>\nLỗi trong vòng lặp chính của bot: {e}")
            graceful_sleep(60)
    
    # Sau khi vòng lặp kết thúc (do shutdown_requested = True), thực hiện dọn dẹp
    perform_final_shutdown(telegram_notifier, config_name)

if __name__ == "__main__":
    main_trader_loop()