import MetaTrader5 as mt5
import pandas as pd
import datetime
import sys

# Fix Unicode errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

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

def get_mt5_data(symbol, timeframe, num_bars):
    """
    Lấy dữ liệu lịch sử từ MT5.
    
    Args:
        symbol (str): Ký hiệu tài sản (ví dụ: 'XAUUSD').
        timeframe (mt5.TIMEFRAME_...): Khung thời gian (ví dụ: mt5.TIMEFRAME_M15).
        num_bars (int): Số lượng thanh nến muốn lấy.
        
    Returns:
        pd.DataFrame: DataFrame chứa dữ liệu OHLCV, hoặc None nếu có lỗi.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None:
        print(f"Không thể lấy dữ liệu cho {symbol} {timeframe}: {mt5.last_error()}")
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
    
    print(f"+++ Đặt lệnh {trade_type} thành công cho {symbol} | Giá: {result.price:.2f} | SL: {sl:.2f} | TP: {tp:.2f} +++")
    if notifier: notifier.send_message(f"<b>[LỆNH MỚI] {trade_type} {symbol}</b>\nLot: {lot}\nGiá vào: {result.price:.2f}\nSL: {sl:.2f}\nTP: {tp:.2f}")
    return True

def modify_position_sltp(position_ticket, new_sl, new_tp, notifier=None):
    """Sửa đổi SL/TP của một lệnh đang mở."""
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

    loss_per_lot = (sl_points / tick_size) * tick_value
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
    
    print(f"Tính toán Lot Size: Balance={balance:.2f}, Risk={risk_percent}%, Risk Amount=${risk_amount:.2f}, Loss/Lot=${loss_per_lot:.2f}, Calculated Lot={lot_size:.4f}, Final Lot={final_lot_size:.2f}")
    return final_lot_size

if __name__ == '__main__':
    # --- Cấu hình thông tin tài khoản Demo MT5 của bạn ---
    # Bạn cần thay thế các giá trị này bằng thông tin tài khoản demo thực tế của bạn.
    # Bạn có thể tạo tài khoản demo miễn phí trực tiếp từ nền tảng MT5.
    MT5_LOGIN = 97919483       # Thay bằng số tài khoản của bạn
    MT5_PASSWORD = "K*3rFwVv" # Thay bằng mật khẩu của bạn
    MT5_SERVER = "MetaQuotes-Demo" # Hoặc tên máy chủ demo của broker của bạn
    
    if connect_to_mt5(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        print("\n--- Kết nối thành công. Tiến hành đặt lệnh thử nghiệm ---")
        
        # Đặt một lệnh MUA thử nghiệm với khối lượng 0.01 lot, SL 10, TP 20
        place_order(symbol="XAUUSD", lot=0.01, trade_type="BUY", sl_points=10.0, tp_points=20.0)
        
        # Đóng kết nối MT5 khi hoàn tất
        mt5.shutdown()
        print("\nĐã ngắt kết nối MT5.")
    else:
        print("Không thể kết nối đến MT5. Vui lòng kiểm tra thông tin đăng nhập và kết nối mạng.")