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

def place_order(symbol, lot, trade_type, price, sl_value, tp_value, notifier=None):
    """
    Thực hiện một lệnh trên MT5 (lệnh thị trường hoặc lệnh chờ).

    Args:
        symbol (str): Ký hiệu.
        lot (float): Khối lượng.
        trade_type (str): 'BUY', 'SELL', 'BUY_LIMIT', 'SELL_LIMIT'.
        price (float): Giá vào lệnh. Đối với lệnh thị trường, có thể để 0 để MT5 tự lấy giá.
                       Đối với lệnh chờ, đây là giá kích hoạt.
        sl_value (float): Mức Stop Loss.
        tp_value (float): Mức Take Profit.
        notifier (TelegramNotifier, optional): Đối tượng để gửi thông báo.

    Returns:
        bool: True nếu thành công, False nếu thất bại.
    """
    if not _ensure_mt5_connection():
        print("Lỗi: Mất kết nối MT5, không thể đặt lệnh.")
        return False

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"Không thể lấy giá tick cho {symbol}")
        return False

    order_type = None
    action = mt5.TRADE_ACTION_DEAL # Mặc định là lệnh thị trường

    # --- Logic để xác định loại lệnh ---
    if trade_type.upper() == 'BUY':
        order_type = mt5.ORDER_TYPE_BUY
        if price == 0: price = tick.ask # Lấy giá thị trường nếu không được chỉ định
    elif trade_type.upper() == 'SELL':
        order_type = mt5.ORDER_TYPE_SELL
        if price == 0: price = tick.bid
    elif trade_type.upper() == 'BUY_LIMIT':
        order_type = mt5.ORDER_TYPE_BUY_LIMIT
        action = mt5.TRADE_ACTION_PENDING
        # Với lệnh BUY LIMIT, giá đặt lệnh phải thấp hơn giá ASK hiện tại
        # LOGIC MỚI: Nếu giá đã vượt qua điểm đặt limit, chuyển sang lệnh thị trường
        if price >= tick.ask:
            print(f"Cảnh báo: Giá BUY LIMIT ({price:.2f}) không hợp lệ (>= Ask {tick.ask:.2f}). Chuyển sang lệnh BUY thị trường.")
            if notifier: notifier.send_message(f"<b>[CHUYỂN LỆNH] Giá BUY LIMIT không hợp lệ. Chuyển sang lệnh BUY thị trường.</b>")
            order_type = mt5.ORDER_TYPE_BUY
            action = mt5.TRADE_ACTION_DEAL
            price = tick.ask # Đặt lệnh tại giá thị trường
    elif trade_type.upper() == 'SELL_LIMIT':
        order_type = mt5.ORDER_TYPE_SELL_LIMIT
        action = mt5.TRADE_ACTION_PENDING
        # Với lệnh SELL LIMIT, giá đặt lệnh phải cao hơn giá BID hiện tại
        # LOGIC MỚI: Nếu giá đã vượt qua điểm đặt limit, chuyển sang lệnh thị trường
        if price <= tick.bid:
            print(f"Cảnh báo: Giá SELL LIMIT ({price:.2f}) không hợp lệ (<= Bid {tick.bid:.2f}). Chuyển sang lệnh SELL thị trường.")
            if notifier: notifier.send_message(f"<b>[CHUYỂN LỆNH] Giá SELL LIMIT không hợp lệ. Chuyển sang lệnh SELL thị trường.</b>")
            order_type = mt5.ORDER_TYPE_SELL
            action = mt5.TRADE_ACTION_DEAL
            price = tick.bid # Đặt lệnh tại giá thị trường
    else:
        print(f"Loại lệnh không hợp lệ: {trade_type}")
        return False

    # --- Logic xác định SL/TP (giữ nguyên, vì ta sẽ truyền giá trị tuyệt đối) ---
    sl = sl_value
    tp = tp_value

    # --- KIỂM TRA STOPS LEVEL (KHOẢNG CÁCH TỐI THIỂU) CHO CẢ LỆNH THỊ TRƯỜNG VÀ LỆNH CHỜ ---
    symbol_info = mt5.symbol_info(symbol)
    stops_level = symbol_info.trade_stops_level * symbol_info.point if symbol_info else 0.0

    if stops_level > 0:
        # Kiểm tra khoảng cách giữa giá đặt lệnh và giá thị trường (đối với lệnh chờ)
        if action == mt5.TRADE_ACTION_PENDING:
            market_price = tick.ask if order_type == mt5.ORDER_TYPE_BUY_LIMIT else tick.bid
            if abs(price - market_price) < stops_level:
                print(f"Lỗi: Giá đặt lệnh chờ ({price:.4f}) quá gần giá thị trường ({market_price:.4f}). Yêu cầu tối thiểu: {stops_level:.4f}. Lệnh bị hủy.")
                if notifier: notifier.send_message(f"<b>[LỖI] Giá đặt lệnh chờ quá gần. Lệnh {trade_type} {symbol} bị hủy.</b>")
                return False
        # Kiểm tra khoảng cách SL/TP so với giá đặt lệnh
        if sl > 0 and abs(price - sl) < stops_level:
            print(f"Lỗi: Khoảng cách SL ({abs(price - sl):.4f}) quá gần giá vào lệnh. Yêu cầu tối thiểu: {stops_level:.4f}. Lệnh bị hủy.")
            if notifier: notifier.send_message(f"<b>[LỖI] Khoảng cách SL quá gần. Lệnh {trade_type} {symbol} bị hủy.</b>")
            return False
        if tp > 0 and abs(price - tp) < stops_level:
            print(f"Lỗi: Khoảng cách TP ({abs(price - tp):.4f}) quá gần giá vào lệnh. Yêu cầu tối thiểu: {stops_level:.4f}. Lệnh bị hủy.")
            if notifier: notifier.send_message(f"<b>[LỖI] Khoảng cách TP quá gần. Lệnh {trade_type} {symbol} bị hủy.</b>")
            return False
    # --- Gửi yêu cầu đặt lệnh ---
    # Làm tròn các giá trị theo yêu cầu của symbol
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        digits = symbol_info.digits
        volume_step = symbol_info.volume_step
        
        # Làm tròn volume theo volume_step và chỉ giữ 2 số thập phân
        lot = float(f"{(round(lot / volume_step) * volume_step):.2f}")
        
        # Làm tròn các giá trị theo digits của symbol
        if price > 0:
            price = float(f"{round(price, digits):.{digits}f}")
        if sl > 0:
            sl = float(f"{round(sl, digits):.{digits}f}")
        if tp > 0:
            tp = float(f"{round(tp, digits):.{digits}f}")

    request = {
        "action": action,
        "symbol": symbol,
        "volume": float(lot),  # Chuyển đổi explicit sang float
        "type": order_type,
        "price": float(price),  # Chuyển đổi explicit sang float
        "sl": float(sl) if sl is not None and sl > 0 else 0.0,
        "tp": float(tp) if tp is not None and tp > 0 else 0.0,
        "magic": 234002,
        "comment": "PyBot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    # --- SỬA LỖI: Làm tròn tất cả các giá trị giá theo yêu cầu của symbol ---
    # Lỗi mt5.order_send() trả về None thường do giá trị price/sl/tp có quá nhiều chữ số thập phân.
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        digits = symbol_info.digits
        if request['price'] > 0:
            request['price'] = round(request['price'], digits)
        if request['sl'] > 0:
            request['sl'] = round(request['sl'], digits)
        if request['tp'] > 0:
            request['tp'] = round(request['tp'], digits)
    else:
        print(f"Cảnh báo: Không thể lấy thông tin symbol '{symbol}' để làm tròn giá. Lệnh có thể bị từ chối.")

    print("\n=== DEBUG: Chi tiết yêu cầu đặt lệnh ===")
    print(f"- Action: {request['action']}")
    print(f"- Symbol: {request['symbol']}")
    print(f"- Volume: {request['volume']}")
    print(f"- Type: {request['type']}")
    print(f"- Price: {request['price']}")
    print(f"- SL: {request['sl']}")
    print(f"- TP: {request['tp']}")
    print(f"- Magic: {request['magic']}")
    print(f"- Comment: {request['comment']}")
    print(f"- Type Time: {request['type_time']}")
    print(f"- Type Filling: {request['type_filling']}")
    
    # Kiểm tra thông tin symbol
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info:
        print("\n=== Thông tin Symbol ===")
        print(f"- Point: {symbol_info.point}")
        print(f"- Digits: {symbol_info.digits}")
        print(f"- Trade Stops Level: {symbol_info.trade_stops_level}")
        print(f"- Volume Step: {symbol_info.volume_step}")
        print(f"- Volume Min: {symbol_info.volume_min}")
        print(f"- Volume Max: {symbol_info.volume_max}")
        
    # Lấy giá tick hiện tại để so sánh
    tick = mt5.symbol_info_tick(symbol)
    if tick:
        print("\n=== Giá Thị Trường Hiện Tại ===")
        print(f"- Bid: {tick.bid}")
        print(f"- Ask: {tick.ask}")
        print(f"- Last: {tick.last}")
    print("===================================\n")
    
    result = mt5.order_send(request)
    if result is None:
        error_code = mt5.last_error()
        print(f"Lỗi đặt lệnh {trade_type}: mt5.order_send() trả về None.")
        print(f"Mã lỗi MT5: {error_code[0]} - {error_code[1]}")
        if notifier: notifier.send_message(f"<b>[LỖI] Đặt lệnh {trade_type} {symbol} thất bại!</b>\nLỗi: {error_code[1]}")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Lỗi đặt lệnh {trade_type}: retcode={result.retcode}, comment={result.comment}")
        if notifier: notifier.send_message(f"<b>[LỖI] Đặt lệnh {trade_type} {symbol} thất bại!</b>\nLỗi: {result.comment}")
        return False
    
    order_kind = "LỆNH CHỜ MỚI" if action == mt5.TRADE_ACTION_PENDING else "LỆNH MỚI"
    # Lấy giá entry đúng - sử dụng giá từ request nếu result.price là 0
    entry_price = result.price if result.price > 0 else request['price']
    
    print(f"--- {order_kind} ĐƯỢC ĐẶT ---")
    print(f"  - Symbol: {symbol}")
    print(f"  - Loại: {trade_type}")
    print(f"  - Volume: {request['volume']:.2f} lots")
    print(f"  - Giá vào: {entry_price:.3f}")
    print(f"  - Stop Loss: {request['sl']:.3f}")
    print(f"  - Take Profit: {request['tp']:.3f}")
    print("--------------------------")
    if notifier: notifier.send_message(
        f"<b>[{order_kind}] {trade_type} {symbol}</b>\n"
        f"Lot: {request['volume']:.2f}\n"
        f"Giá vào: {entry_price:.3f}\n"
        f"SL: {request['sl']:.3f}\n"
        f"TP: {request['tp']:.3f}"
    )
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
    if result is None:
        print(f"Lỗi đóng lệnh #{position.ticket}: mt5.order_send() trả về None. Có thể do lỗi kết nối hoặc yêu cầu không hợp lệ.")
        if notifier: notifier.send_message(f"<b>[LỖI] Đóng lệnh #{position.ticket} thất bại!</b>\nLỗi: mt5.order_send() trả về None.")
        return False

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

def calculate_dynamic_lot_size(symbol, stop_loss_price, trading_params, peak_equity, session_multiplier=1.0):
    """
    Tính toán khối lượng lệnh động dựa trên logic phức tạp từ backtester.
    Bao gồm: % rủi ro, giới hạn rủi ro min/max, giảm rủi ro khi sụt giảm,
    hệ số nhân theo phiên, và so sánh lot an toàn.
    """
    if not _ensure_mt5_connection(): return None

    account_info = mt5.account_info()
    symbol_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if not all([account_info, symbol_info, tick]):
        print("Lỗi: Không thể lấy thông tin tài khoản, symbol hoặc giá tick.")
        return None

    balance = account_info.balance

    # Xác định hướng giao dịch và giá vào lệnh dự kiến
    is_buy_trade = stop_loss_price < tick.bid
    entry_price = tick.ask if is_buy_trade else tick.bid

    if entry_price <= 0:
        print(f"Lỗi: Giá vào lệnh không hợp lệ ({entry_price}). Bỏ qua tính toán.")
        return None

    # --- Lấy các tham số từ config ---
    risk_percent = trading_params.get('risk_percent', 1.0)
    min_risk_percent = trading_params.get('min_risk_percent', 1.5)
    max_risk_percent = trading_params.get('max_risk_percent', 4.0)
    drawdown_reducer_tiers = sorted(trading_params.get('drawdown_reducer_tiers', []), key=lambda x: x['threshold_percent'], reverse=True)
    target_sl_distance_points = trading_params.get('target_sl_distance_points', 4.0)
    contract_size = symbol_info.trade_contract_size
    min_position_size = symbol_info.volume_min
    max_position_size = symbol_info.volume_max
    volume_step = symbol_info.volume_step

    # --- Drawdown Reducer Logic (giống hệt trong backtester) ---
    risk_multiplier = 1.0
    drawdown_percent = (peak_equity - balance) / peak_equity * 100 if peak_equity > 0 else 0
    if drawdown_percent > 0:
        for tier in drawdown_reducer_tiers:
            if drawdown_percent >= tier['threshold_percent']:
                risk_multiplier = tier['factor']
                print(f"Info: Drawdown {drawdown_percent:.2f}% >= {tier['threshold_percent']}%. Áp dụng hệ số rủi ro x{risk_multiplier}.")
                break # Áp dụng bậc giảm rủi ro cao nhất

    # --- Tính toán số tiền rủi ro ---
    target_risk_amount = balance * (risk_percent / 100.0) * risk_multiplier * session_multiplier
    min_risk_amount = balance * (min_risk_percent / 100.0)
    max_risk_amount = balance * (max_risk_percent / 100.0)
    risk_amount = max(min_risk_amount, min(target_risk_amount, max_risk_amount))
    print(f"Info: Session Multiplier x{session_multiplier}. Risk amount clamped to ${risk_amount:.2f}")
    
    # --- Logic tính toán Lot Size an toàn ---
    # SỬA LỖI LOGIC: Luôn chọn khoảng cách SL XA HƠN để tính lot size AN TOÀN HƠN
    strategy_sl_distance_points = abs(entry_price - stop_loss_price)
    if strategy_sl_distance_points <= 0:
        print(f"Lỗi: Khoảng cách SL của chiến lược không hợp lệ ({strategy_sl_distance_points}). Bỏ qua.")
        return None

    # Chọn khoảng cách SL xa hơn giữa SL của chiến lược và SL mục tiêu
    effective_sl_distance = max(strategy_sl_distance_points, target_sl_distance_points)
    print(f"Info: SL chiến lược: {strategy_sl_distance_points:.2f}, SL mục tiêu: {target_sl_distance_points:.2f}. Chọn SL hiệu dụng: {effective_sl_distance:.2f} để tính lot.")

    # Tính toán lot size dựa trên khoảng cách SL an toàn nhất
    loss_per_lot = effective_sl_distance * contract_size
    raw_position_size = risk_amount / loss_per_lot if loss_per_lot > 0 else 0.0

    # Mức SL cuối cùng để đặt lệnh là SL ban đầu từ chiến lược
    # SỬA LỖI LOGIC: Nếu SL hiệu dụng LỚN HƠN SL của chiến lược (để có lot an toàn hơn),
    # thì chúng ta phải tính toán lại giá SL cuối cùng để nó phản ánh đúng khoảng cách an toàn đó.
    if effective_sl_distance > strategy_sl_distance_points:
        final_stop_loss_price = entry_price - effective_sl_distance if is_buy_trade else entry_price + effective_sl_distance
    else:
        # Nếu không, SL của chiến lược là đủ an toàn, giữ nguyên nó.
        final_stop_loss_price = stop_loss_price

    # Áp dụng giới hạn min/max và làm tròn
    position_size = max(min_position_size, min(raw_position_size, max_position_size))
    position_size = round(position_size / volume_step) * volume_step

    if position_size <= 0:
        print("Cảnh báo: Khối lượng lệnh tính được bằng 0. Bỏ qua giao dịch.")
        return None

    # --- KIỂM TRA AN TOÀN CUỐI CÙNG ---
    # Kiểm tra xem rủi ro thực tế với lot size cuối cùng có vượt quá mức trần không.
    final_risk_amount = position_size * abs(entry_price - final_stop_loss_price) * contract_size
    if final_risk_amount > max_risk_amount * 1.01: # Thêm 1% dung sai cho các lỗi làm tròn
        print(f"CẢNH BÁO AN TOÀN: Lot size cuối cùng ({position_size:.2f}) làm rủi ro thực tế (${final_risk_amount:.2f}) vượt quá mức trần cho phép (${max_risk_amount:.2f}). Bỏ qua tín hiệu.")
        return None

    print(f"Final Calculation: Lot Size={position_size:.2f}, Stop Loss Price={final_stop_loss_price:.2f}")
    return position_size, final_stop_loss_price


if __name__ == '__main__':
    # --- Chạy thử nghiệm kết nối và đặt lệnh bằng cấu hình từ config.json ---
    from config_manager import get_config

    print("--- Đang chạy thử nghiệm mt5_connector.py ---")
    config = get_config()
    if not config:
        print("Lỗi: Không thể tải tệp cấu hình 'config.json'.")
    else:
        # Lấy thông tin đăng nhập và giao dịch từ config
        mt5_credentials = config.get('mt5_credentials', {})
        trading_params = config.get('trading', {})
        login = mt5_credentials.get('login')
        password = mt5_credentials.get('password')
        server = mt5_credentials.get('server')
        symbol_to_trade = trading_params.get('symbol', 'XAUUSD') # Lấy symbol từ config

        if connect_to_mt5(login, password, server):
            print(f"\n--- Kết nối thành công. Tiến hành đặt lệnh thử nghiệm cho {symbol_to_trade} ---")
            
            # Thực hiện lệnh BUY 0.01 lot theo yêu cầu
            # SL và TP được đặt ở mức 10 và 20 giá để kiểm tra
            place_order(symbol=symbol_to_trade, lot=0.01, trade_type="BUY", sl_value=10.0, tp_value=20.0, notifier=None)
            
            mt5.shutdown()
            print("\nĐã ngắt kết nối MT5.")
        else:
            print("\nKhông thể kết nối đến MT5. Vui lòng kiểm tra thông tin trong 'config.json' và kết nối mạng.")