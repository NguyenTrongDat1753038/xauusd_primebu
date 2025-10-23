import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import os
import sys

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from mt5_connector import connect_to_mt5

def download_and_save_data():
    """
    Kết nối đến MT5, tải dữ liệu lịch sử cho nhiều khung thời gian,
    định dạng lại và lưu vào các tệp CSV trong thư mục 'Data'.
    """
    # --- Tải cấu hình MT5 ---
    config = get_config()
    if not config:
        print("Không thể tải cấu hình.")
        return

    mt5_credentials = config.get('mt5_credentials', {})
    
    # --- Cấu hình dữ liệu cần tải ---
    SYMBOL = "XAUUSD"
    START_DATE = datetime(2021, 1, 1)
    END_DATE = datetime.now()

    TIMEFRAMES = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }

    # --- Kết nối đến MT5 ---
    if not connect_to_mt5(mt5_credentials.get('login'), mt5_credentials.get('password'), mt5_credentials.get('server')):
        print("Không thể kết nối đến MT5. Vui lòng kiểm tra lại.")
        return

    print("\n--- Bắt đầu quá trình tải dữ liệu ---")

    # --- Vòng lặp tải và lưu dữ liệu ---
    for tf_name, tf_enum in TIMEFRAMES.items():
        print(f"Đang tải dữ liệu cho {SYMBOL} - {tf_name}...")
        
        # Tải dữ liệu từ ngày bắt đầu đến ngày kết thúc
        rates = mt5.copy_rates_range(SYMBOL, tf_enum, START_DATE, END_DATE)
        
        if rates is None or len(rates) == 0:
            print(f"Không tải được dữ liệu cho {tf_name}. Bỏ qua.")
            continue

        # Chuyển đổi sang DataFrame của pandas
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')

        # --- Định dạng lại theo cấu trúc yêu cầu của data_loader.py ---
        df_to_save = pd.DataFrame()
        df_to_save['<DATE>'] = df['time'].dt.strftime('%Y.%m.%d')
        # Chỉ thêm cột TIME cho các khung thời gian intraday
        if tf_name != 'D1':
            df_to_save['<TIME>'] = df['time'].dt.strftime('%H:%M:%S')
        
        df_to_save['<OPEN>'] = df['open']
        df_to_save['<HIGH>'] = df['high']
        df_to_save['<LOW>'] = df['low']
        df_to_save['<CLOSE>'] = df['close']
        
        # Tạo tên tệp
        start_str = START_DATE.strftime('%Y%m%d')
        end_str = END_DATE.strftime('%Y%m%d')
        output_filename = f"Data/{SYMBOL}_{tf_name}_{start_str}_{end_str}.csv"

        # Lưu vào tệp CSV với định dạng tab-separated
        try:
            df_to_save.to_csv(output_filename, sep='\t', index=False)
            print(f"[*] Đã lưu thành công {len(df_to_save)} dòng vào: {output_filename}\n")
        except Exception as e:
            print(f"[!] Lỗi khi lưu tệp {output_filename}: {e}\n")

    # --- Dọn dẹp ---
    mt5.shutdown()
    print("[*] Đã ngắt kết nối khỏi MT5.")
    print("--- Hoàn tất ---")

if __name__ == "__main__":
    download_and_save_data()