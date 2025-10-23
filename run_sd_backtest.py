import os
import sys
import argparse
import glob

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_analysis_data # Sử dụng hàm phân tích chính
from strategies import SupplyDemandStrategy # Use the new Supply/Demand strategy
from backtester import Backtester

def find_latest_file(pattern):
    """Finds the most recently modified file matching a pattern."""
    try:
        list_of_files = glob.glob(pattern)
        if not list_of_files:
            return None
        return max(list_of_files, key=os.path.getctime)
    except Exception:
        return None

def run_backtest(output_path=None):
    """Chạy backtest cho chiến lược Cung/Cầu (Supply/Demand)."""
    print("--- Bắt đầu Backtest cho Chiến lược Supply/Demand ---")

    # 1. Tải cấu hình
    config = get_config()
    if not config:
        return

    # 2. Tải dữ liệu cho các khung thời gian M15, H1, H4
    print("Đang tải dữ liệu...")
    data_dir = os.path.join(project_root, 'Data')

    timeframe_patterns = {
        'm15': os.path.join(data_dir, 'XAUUSD_M15_*.csv'),
        'h4': os.path.join(data_dir, 'XAUUSD_H4_*.csv'),
        'd1': os.path.join(data_dir, 'XAUUSD_D1_*.csv'),
    }
    
    timeframes_data = {}
    for tf, pattern in timeframe_patterns.items():
        latest_file = find_latest_file(pattern)
        if not latest_file:
            print(f"Error: No data file found for timeframe {tf.upper()} with pattern {pattern}")
            return
        df = load_csv_data(latest_file)
        if df is None:
            return
        timeframes_data[tf] = df

    # 3. Chuẩn bị dữ liệu đã được phân tích
    strategy_params = config.get('strategy', {})
    # Lấy sr_periods từ config, nếu không có thì dùng giá trị mặc định
    sr_periods = strategy_params.get('sr_periods', {'m15': 200, 'h1': 50, 'h4': 50})
    prepared_data = prepare_analysis_data(timeframes_data, sr_periods, include_sd_zones=True)
    
    if prepared_data is None or prepared_data.empty:
        return

    # 4. Khởi tạo chiến lược
    strategy = SupplyDemandStrategy(strategy_params)

    # 5. Khởi tạo và chạy Backtester
    trading_params = config.get('trading', {})
    backtester = Backtester(strategy=strategy, data=prepared_data, trading_params=trading_params)
    backtester.run()

    # 6. Lưu báo cáo nếu có đường dẫn đầu ra
    if output_path:
        backtester.save_report_to_csv(output_path)

if __name__ == "__main__":
    # Chạy backtest và lưu kết quả vào tệp 'sd_backtest_report.csv'
    # trong thư mục 'reports'
    run_backtest(output_path="reports/sd_backtest_report.csv")