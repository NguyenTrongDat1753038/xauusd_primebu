import MetaTrader5 as mt5
import pandas as pd
import datetime
import sys
import time

# Fix Unicode errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Biến toàn cục để lưu trữ thông tin đăng nhập cho việc kết nối lại tự động
_login_credentials = {
    "login": None, "password": None, "server": None
}

def connect_to_mt5(login, password, server):
    """
    Kết nối đến MetaTrader 5 với thông tin đăng nhập được cung cấp.
    
    Args:
        login (int): Số tài khoản MT5.
        password (str): Mật khẩu tài khoản MT5.
        server (str): Tên máy chủ MT5 (ví dụ: 'MetaQuotes-Demo').
        
    Returns:
        bool: True nếu kết nối thành công, False nếu ngược lại.
    """
    global _login_credentials
    # Lưu thông tin đăng nhập để có thể sử dụng cho việc kết nối lại
    _login_credentials["login"] = login
    _login_credentials["password"] = password
    _login_credentials["server"] = server

    if not mt5.initialize():
        print(f"Lỗi khởi tạo MT5: {mt5.last_error()}")
        return False
    
    # Kết nối đến tài khoản giao dịch
    authorized = mt5.login(login, password=password, server=server)
    if not authorized:
        print(f"Lỗi đăng nhập vào tài khoản #{login} trên máy chủ {server}: {mt5.last_error()}")
        mt5.shutdown()
        return False
    
    print(f"Đã kết nối thành công đến tài khoản #{login} trên máy chủ {server}")
    return True

def _ensure_mt5_connection():
    """
    Đảm bảo rằng kết nối MT5 đang hoạt động.
    Hàm này kiểm tra trạng thái terminal và trả về True nếu OK, False nếu không.
    Nếu mất kết nối, nó sẽ cố gắng kết nối và đăng nhập lại.
    """
    terminal_info = mt5.terminal_info()
    if terminal_info is None or not terminal_info.connected:
        print("CẢNH BÁO: Mất kết nối MT5. Đang thử kết nối và đăng nhập lại...")
        # Cố gắng kết nối lại với thông tin đã lưu
        if _login_credentials["login"]:
            # Thử khởi tạo lại trước khi đăng nhập
            if not mt5.initialize():
                print(f"Lỗi khởi tạo lại MT5: {mt5.last_error()}")
                return False
            # Đăng nhập lại
            return connect_to_mt5(
                _login_credentials["login"],
                _login_credentials["password"],
                _login_credentials["server"]
            )
        else:
            print("Lỗi: Không có thông tin đăng nhập để kết nối lại.")
            return False
    return True

# Từ điển ánh xạ chuỗi khung thời gian sang hằng số của MetaTrader5
TIMEFRAME_MAP = {
    'm1': mt5.TIMEFRAME_M1,
    'm5': mt5.TIMEFRAME_M5,
    'm15': mt5.TIMEFRAME_M15,
    'm30': mt5.TIMEFRAME_M30,
    'h1': mt5.TIMEFRAME_H1,
    'h4': mt5.TIMEFRAME_H4,
    'd1': mt5.TIMEFRAME_D1,
    'w1': mt5.TIMEFRAME_W1,
    'mn1': mt5.TIMEFRAME_MN1
}

def get_mt5_data(symbol, timeframe_str, num_bars):
    """
    Lấy dữ liệu lịch sử từ MT5, đảm bảo symbol được hiển thị trong Market Watch.
    
    Args:
        symbol (str): Ký hiệu tài sản (ví dụ: 'XAUUSD').
        timeframe_str (str): Chuỗi đại diện khung thời gian (ví dụ: 'm1', 'h4').
        num_bars (int): Số lượng thanh nến muốn lấy.
        
    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu OHLCV, hoặc None nếu có lỗi.
    """
    # Đảm bảo kết nối MT5 vẫn còn hoạt động
    if not _ensure_mt5_connection():
        print("Lỗi: Không thể thiết lập lại kết nối MT5. Bỏ qua việc lấy dữ liệu.")
        return None

    # --- Kiểm tra và kích hoạt Symbol ---
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Lỗi: Symbol '{symbol}' không tồn tại trên sàn. Kiểm tra lại tên symbol.")
        return None

    if not symbol_info.visible:
        print(f"Cảnh báo: Symbol '{symbol}' chưa được hiển thị trong Market Watch. Đang thử kích hoạt...")
        if not mt5.symbol_select(symbol, True):
            print(f"Lỗi: Không thể kích hoạt symbol '{symbol}' trong Market Watch.")
            return None
        print(f"Đã kích hoạt '{symbol}' thành công. Chờ 1 giây để terminal cập nhật...")
        time.sleep(1) # Cho terminal thời gian để cập nhật

    # --- Lấy dữ liệu ---
    timeframe = TIMEFRAME_MAP.get(timeframe_str.lower())
    if timeframe is None:
        print(f"Lỗi: Khung thời gian '{timeframe_str}' không hợp lệ.")
        return None

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None or len(rates) == 0: # Kiểm tra cả trường hợp trả về mảng rỗng
        print(f"Không thể lấy dữ liệu cho {symbol} {timeframe_str.upper()}: {mt5.last_error()}")
        # Thử lại với một số lượng nhỏ hơn để "warm-up"
        print("Thử lấy một lượng dữ liệu nhỏ hơn để 'warm-up' chart...")
        warmup_rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 10)
        if warmup_rates is None or len(warmup_rates) == 0:
            print("Warm-up thất bại. Vui lòng kiểm tra lại symbol và dữ liệu trên terminal.")
            return None
        else:
            print("Warm-up thành công. Dữ liệu có thể chưa đủ, sẽ thử lại ở lần sau.")
            # Trả về None để vòng lặp chính thử lại sau
            return None

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'OPEN', 'high': 'HIGH', 'low': 'LOW', 'close': 'CLOSE', 'tick_volume': 'VOLUME'}, inplace=True)
    return df[['OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME']]

def place_order(symbol, lot, trade_type, sl_value, tp_value, notifier=None):
    """Thực hiện một lệnh trên MT5."""
    """
    Thực hiện một lệnh trên MT5.
    Hàm này có thể xử lý cả giá trị SL/TP tuyệt đối (ví dụ: 1905.5) và khoảng cách điểm (ví dụ: 38.0).
    """
    tick = mt5.symbol_info_tick(symbol)
    # Đảm bảo kết nối trước khi thực hiện hành động
    if not _ensure_mt5_connection():
        print("Lỗi: Mất kết nối MT5, không thể đặt lệnh.")
        return False

    if tick is None:
        print(f"Không thể lấy giá tick cho {symbol}")
        return False

    order_type = None
    price = 0
    sl = 0.0
    tp = 0.0

    # --- Logic để xác định loại lệnh và giá ---
    if trade_type.upper() == 'BUY':
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        # Nếu sl_value là một mức giá tuyệt đối (ví dụ: 1900.50)
        if sl_value > 1000:
            sl = sl_value
        # Nếu sl_value là một khoảng cách điểm (ví dụ: 38.0)
        else:
            sl = price - sl_value
        
        if tp_value > 1000:
            tp = tp_value
        else:
            tp = price + tp_value

    elif trade_type.upper() == 'SELL':
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        if sl_value > 1000:
            sl = sl_value
        else:
            sl = price + sl_value

        if tp_value > 1000:
            tp = tp_value
        else:
            tp = price - tp_value
    else:
        print(f"Loại lệnh không hợp lệ: {trade_type}")
        return False

    # --- Gửi yêu cầu đặt lệnh ---
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 234002, # Magic number để nhận diện lệnh của bot
        "comment": "Placed by Python Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Lỗi đặt lệnh {trade_type}: retcode={result.retcode}, comment={result.comment}")
        if notifier: notifier.send_message(f"<b>[LỖI] Đặt lệnh {trade_type} {symbol} thất bại!</b>\nLỗi: {result.comment}")
        return False
    
    print("--- LỆNH MỚI ĐƯỢC ĐẶT ---")
    print(f"  - Symbol: {symbol}")
    print(f"  - Loại: {trade_type}")
    print(f"  - Volume: {lot:.2f} lots")
    print(f"  - Giá vào: {result.price:.2f}")
    print(f"  - Stop Loss: {sl:.2f}")
    print(f"  - Take Profit: {tp:.2f}")
    print("--------------------------")
    if notifier: notifier.send_message(f"<b>[LỆNH MỚI] {trade_type} {symbol}</b>\nLot: {lot}\nGiá vào: {result.price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}")
    return True

def modify_position_sltp(position_ticket, new_sl, new_tp, notifier=None):
    """Sửa đổi SL/TP của một lệnh đang mở."""
    # Đảm bảo kết nối trước khi thực hiện hành động
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
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Lỗi sửa SL/TP lệnh #{position_ticket}: retcode={result.retcode}, comment={result.comment}")
        if notifier: notifier.send_message(f"<b>[LỖI] Sửa SL/TP lệnh #{position_ticket} thất bại!</b>\nLỗi: {result.comment}")
        return False

    print(f"*** Sửa lệnh #{position_ticket} thành công | SL mới: {new_sl} | TP mới: {new_tp} ***")
    if notifier: notifier.send_message(f"<b>[CẬP NHẬT LỆNH] Lệnh #{position_ticket}</b>\nSL mới: {new_sl}\nTP mới: {new_tp}")
    return True

def close_position(position, notifier=None, comment="Closed by bot"):
    """Đóng một lệnh đang mở."""
    # Đảm bảo kết nối trước khi thực hiện hành động
    if not _ensure_mt5_connection():
        print("Lỗi: Mất kết nối MT5, không thể đóng lệnh.")
        return False

    tick = mt5.symbol_info_tick(position.symbol)
    if tick is None:
        print(f"Không thể lấy giá tick cho {position.symbol} để đóng lệnh.")
        return False

    # Xác định loại lệnh đối ứng
    if position.type == mt5.ORDER_TYPE_BUY:
        trade_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        trade_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "position": position.ticket,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": trade_type,
        "price": price,
        "magic": 234002,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Lỗi đóng lệnh #{position.ticket}: retcode={result.retcode}, comment={result.comment}")
        if notifier: notifier.send_message(f"<b>[LỖI] Đóng lệnh #{position.ticket} thất bại!</b>\nLỗi: {result.comment}")
        return False

    print(f"--- Đóng lệnh #{position.ticket} thành công ---")
    if notifier: notifier.send_message(f"<b>[ĐÓNG LỆNH] Lệnh #{position.ticket}</b>\nLoại: {'BUY' if position.type == mt5.ORDER_TYPE_BUY else 'SELL'}\nGiá vào: {position.price_open}\nGiá đóng: {price}")
    return True

def calculate_lot_size(symbol, sl_points, risk_percent):
    """
    Tính toán khối lượng lệnh (lot size) dựa trên phần trăm rủi ro.
    
    Args:
        symbol (str): Ký hiệu tài sản.
        sl_points (float): Khoảng cách dừng lỗ tính bằng điểm giá (ví dụ: 38.0 cho XAUUSD).
        risk_percent (float): Phần trăm rủi ro trên mỗi lệnh (ví dụ: 1.0 cho 1%).

    Returns:
        float: Khối lượng lệnh đã được tính toán và làm tròn, hoặc None nếu có lỗi.
    """
    # Đảm bảo kết nối trước khi thực hiện hành động
    if not _ensure_mt5_connection():
        print("Lỗi: Mất kết nối MT5, không thể tính toán lot size.")
        return None

    account_info = mt5.account_info()
    if account_info is None:
        print("Không thể lấy thông tin tài khoản.")
        return None

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Không thể lấy thông tin cho symbol {symbol}.")
        return None

    balance = account_info.balance
    risk_amount = balance * (risk_percent / 100.0)
    
    # Giá trị của 1 tick cho 1 lot
    tick_value = symbol_info.trade_tick_value
    tick_size = symbol_info.trade_tick_size

    if tick_size == 0:
        print(f"Lỗi: Tick size cho {symbol} bằng 0.")
        return None
        
    # Lớp bảo vệ quan trọng: Nếu khoảng cách SL quá nhỏ, bỏ qua để tránh lỗi tính toán lot size hoặc lệnh bị từ chối.
    # Đối với XAUUSD, 0.1 USD là 10 pips, thường là mức tối thiểu hợp lý.
    if sl_points < 0.1: 
        print(f"CẢNH BÁO: Khoảng cách SL quá nhỏ ({sl_points:.4f} USD). Bỏ qua tính toán lot size để tránh lỗi.")
        return None

    # Tính toán giá trị thua lỗ cho 1 lot nếu SL bị chạm
    # sl_points là khoảng cách giá (ví dụ: 10.0 cho 10 USD)
    # symbol_info.trade_contract_size là kích thước hợp đồng (ví dụ: 100 cho XAUUSD)
    if not hasattr(symbol_info, 'trade_contract_size') or symbol_info.trade_contract_size <= 0:
        print(f"CẢNH BÁO: Không thể lấy trade_contract_size cho {symbol}. Sử dụng tính toán thay thế.")
        loss_per_lot = (sl_points / tick_size) * tick_value # Fallback to original (potentially incorrect) calculation
    else:
        loss_per_lot = sl_points * symbol_info.trade_contract_size

    if loss_per_lot <= 0:
        print(f"Lỗi: Giá trị thua lỗ mỗi lot không hợp lệ ({loss_per_lot:.2f}). Kiểm tra lại sl_points.")
        return None

    lot_size = risk_amount / loss_per_lot

    # Làm tròn khối lượng lệnh theo bước nhảy cho phép của symbol
    lot_step = symbol_info.volume_step
    rounded_lot_size = round(lot_size / lot_step) * lot_step
    
    # Đảm bảo không vượt quá giới hạn lot tối thiểu/tối đa
    min_lot = symbol_info.volume_min
    max_lot = symbol_info.volume_max
    
    final_lot_size = max(min_lot, min(rounded_lot_size, max_lot))
    
    print(f"Tính toán Lot Size: Balance={balance:.2f}, Risk={risk_percent}%, Risk Amount=${risk_amount:.2f}, SL Distance={sl_points:.2f}, Loss/Lot=${loss_per_lot:.2f}, Calculated Lot={lot_size:.4f}, Final Lot={final_lot_size:.2f}")
    return final_lot_size

if __name__ == '__main__':
    # --- Chạy thử nghiệm kết nối và đặt lệnh bằng cấu hình từ config.json ---
    from config_manager import get_config

    print("--- Đang chạy thử nghiệm mt5_connector.py ---")
    config = get_config()
    if not config:
        print("Lỗi: Không thể tải tệp cấu hình 'config.json'.")
    else:
        mt5_credentials = config.get('mt5_credentials', {})
        login = mt5_credentials.get('login')
        password = mt5_credentials.get('password')
        server = mt5_credentials.get('server')

        if connect_to_mt5(login, password, server):
            print("\n--- Kết nối thành công. Tiến hành đặt lệnh thử nghiệm ---")
            place_order(symbol="XAUUSD", lot=0.01, trade_type="BUY", sl_value=10.0, tp_value=20.0)
            mt5.shutdown()
            print("\nĐã ngắt kết nối MT5.")
        else:
            print("\nKhông thể kết nối đến MT5. Vui lòng kiểm tra thông tin trong 'config.json' và kết nối mạng.")