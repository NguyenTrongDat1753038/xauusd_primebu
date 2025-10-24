import os
import sys
import glob

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_scalping_data
from backtester import Backtester
from strategies import ScalpingEmaCrossoverStrategy, ScalpingRsiPullbackStrategy
from combined_strategy import CombinedScalpingStrategy

# Import các lớp chiến thuật có thể sử dụng M1 trigger
from mtf_ema_m1_trigger_strategy import MTF_EMA_M1_Trigger_Strategy
from m15_filtered_scalping_strategy import M15FilteredScalpingStrategy

# Ánh xạ tên chiến thuật trong config với lớp Python tương ứng
# Hợp nhất tất cả các chiến lược scalping vào một map
STRATEGY_MAP = {
    "MTF_EMA_M1_Trigger_Strategy": MTF_EMA_M1_Trigger_Strategy,
    "M15FilteredScalpingStrategy": M15FilteredScalpingStrategy,
    "ScalpingEmaCrossoverStrategy": ScalpingEmaCrossoverStrategy,
    "ScalpingRsiPullbackStrategy": ScalpingRsiPullbackStrategy,
    "CombinedScalpingStrategy": CombinedScalpingStrategy,
}

def find_latest_file(pattern):
    """Tìm file được chỉnh sửa gần đây nhất khớp với một mẫu."""
    try:
        list_of_files = glob.glob(pattern)
        if not list_of_files:
            return None
        return max(list_of_files, key=os.path.getctime)
    except Exception:
        return None

def run_scalping_backtest(start_date_str=None, output_path_prefix="reports/"):
    """
    Chạy backtest cho tất cả các chiến thuật scalping/M1 Trigger.
    """
    print("--- Bắt đầu Backtest cho các chiến thuật Scalping ---")

    # 1. Tải cấu hình
    config = get_config()
    if not config:
        return

    strategy_config = config.get('strategy', {})
    trading_params = config.get('trading', {})
    active_strategy_name = strategy_config.get('active_strategy')

    StrategyClass = STRATEGY_MAP.get(active_strategy_name)
    if not StrategyClass:
        print(f"Lỗi: Chiến thuật '{active_strategy_name}' không được hỗ trợ bởi script này. Vui lòng chạy run_ema_backtest.py.")
        return

    # 2. Tải và chuẩn bị dữ liệu
    print("Đang tải và chuẩn bị dữ liệu đa khung thời gian (M1, M5, M15, M30, H1)...")
    data_dir = os.path.join(project_root, 'Data')
    
    # Tải tất cả các khung thời gian cần thiết cho các chiến lược scalping/trigger
    timeframe_patterns = {
        'm1': os.path.join(data_dir, 'XAUUSD_M1_*.csv'),
        'm5': os.path.join(data_dir, 'XAUUSD_M5_*.csv'),
        'm15': os.path.join(data_dir, 'XAUUSD_M15_*.csv'),
        'm30': os.path.join(data_dir, 'XAUUSD_M30_*.csv'),
        'h1': os.path.join(data_dir, 'XAUUSD_H1_*.csv'),
    }
    timeframes_data = {}
    for tf, pattern in timeframe_patterns.items():
        latest_file = find_latest_file(pattern)
        if not latest_file:
            print(f"Lỗi: Không tìm thấy file dữ liệu cho khung thời gian {tf.upper()}")
            return
        df = load_csv_data(latest_file)
        if df is None: return
        timeframes_data[tf] = df
    
    strategy_params = strategy_config.get(active_strategy_name, {})
    prepared_data = prepare_scalping_data(timeframes_data, strategy_params)

    if start_date_str:
        print(f"Lọc dữ liệu từ ngày: {start_date_str}")
        prepared_data = prepared_data[prepared_data.index >= start_date_str]

    # 3. Khởi tạo và chạy Backtester
    strategy = StrategyClass(strategy_params)
    backtester = Backtester(strategy=strategy, data=prepared_data, trading_params=trading_params)
    backtester.run()

    # 4. Lưu báo cáo
    output_filename = os.path.join(output_path_prefix, f"{active_strategy_name}_report.csv")
    backtester.save_report_to_csv(output_filename)
    print(f"--- Backtest hoàn tất. Báo cáo đã được lưu tại: {output_filename} ---")

if __name__ == "__main__":
    # Đảm bảo bạn đã kích hoạt một chiến lược scalping trong config.json
    run_scalping_backtest(start_date_str="2025-08-01")