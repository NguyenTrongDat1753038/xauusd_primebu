
import MetaTrader5 as mt5
import sys
import os

# Thêm thư mục src vào sys.path để có thể import từ config_manager
# Lấy đường dẫn đến thư mục gốc của dự án (nơi chứa file list_symbols.py)
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.append(src_path)

from config_manager import get_config

# Fix Unicode errors on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    """Kết nối MT5 và liệt kê tất cả các symbol."""
    config = get_config()
    if not config:
        return

    mt5_credentials = config.get('mt5_credentials', {})
    login = mt5_credentials.get('login')
    password = mt5_credentials.get('password')
    server = mt5_credentials.get('server')

    if not login or not password or not server:
        print("Lỗi: Thông tin đăng nhập MT5 bị thiếu trong 'configs/config.json'.")
        return

    # Khởi tạo kết nối
    if not mt5.initialize():
        print(f"Lỗi khởi tạo MT5: {mt5.last_error()}")
        return

    # Đăng nhập
    if not mt5.login(login, password=password, server=server):
        print(f"Lỗi đăng nhập vào tài khoản #{login}: {mt5.last_error()}")
        mt5.shutdown()
        return

    print(f"--- Đã kết nối thành công đến tài khoản #{login} ---")
    print("--- Đang lấy danh sách các symbol có sẵn ---")

    try:
        # Lấy tất cả các symbol
        symbols = mt5.symbols_get()
        if symbols:
            print(f"Tìm thấy {len(symbols)} symbol:")
            # Sắp xếp symbols theo tên để dễ tìm
            sorted_symbols = sorted(symbols, key=lambda s: s.name)
            for symbol in sorted_symbols:
                # In tên và mô tả để người dùng dễ nhận biết
                print(f"- {symbol.name}: {symbol.description}")
        else:
            print("Không tìm thấy symbol nào.")

    except Exception as e:
        print(f"Có lỗi xảy ra khi lấy danh sách symbol: {e}")

    finally:
        # Ngắt kết nối
        mt5.shutdown()
        print("\n--- Đã ngắt kết nối khỏi MT5 ---")

if __name__ == "__main__":
    main()
