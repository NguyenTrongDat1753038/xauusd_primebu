import os
import sys
import argparse
import glob

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_scalping_data
from strategies import ScalpingEmaCrossoverStrategy, ScalpingRsiPullbackStrategy # Import both strategies
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

def run_backtest(start_date_str=None, output_path=None):
    """Chạy backtest cho chiến lược scalping."""
    print("--- Bắt đầu Backtest cho Chiến lược Scalping EMA Crossover ---")

    # 1. Tải cấu hình
    config = get_config()
    if not config:
        return

    # 2. Tải dữ liệu cho các khung thời gian M1, M5, M15
    print("Đang tải dữ liệu...")
    data_dir = os.path.join(project_root, 'Data')

    timeframe_patterns = {
        'm1': os.path.join(data_dir, 'XAUUSD_M1_*.csv'),
        'm5': os.path.join(data_dir, 'XAUUSD_M5_*.csv'),
        'm15': os.path.join(data_dir, 'XAUUSD_M15_*.csv'),
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
    strategy_config = config.get('strategy', {})
    active_strategy_name = strategy_config.get('active_strategy', 'ScalpingEmaCrossoverStrategy')
    specific_strategy_params = strategy_config.get(active_strategy_name, {})

    # Dùng tham số của chiến lược đang active để chuẩn bị dữ liệu
    prepared_data = prepare_scalping_data(timeframes_data, specific_strategy_params)
    
    if prepared_data is None or prepared_data.empty:
        return

    # Lọc dữ liệu theo ngày bắt đầu nếu được cung cấp
    if start_date_str:
        # Chuyển đổi start_date_str sang datetime để so sánh an toàn
        prepared_data = prepared_data[prepared_data.index >= start_date_str]
        print(f"Dữ liệu được lọc từ ngày: {start_date_str}. Tổng số nến: {len(prepared_data)}")

    # 4. Khởi tạo chiến lược
    print(f"Đang chạy backtest cho chiến lược: {active_strategy_name}")
    if active_strategy_name == 'ScalpingEmaCrossoverStrategy':
        strategy = ScalpingEmaCrossoverStrategy(specific_strategy_params)
    elif active_strategy_name == 'ScalpingRsiPullbackStrategy':
        strategy = ScalpingRsiPullbackStrategy(specific_strategy_params)
    else:
        print(f"Lỗi: Chiến lược '{active_strategy_name}' không được hỗ trợ trong tệp backtest này.")
        return

    # 5. Khởi tạo và chạy Backtester
    trading_params = config.get('trading', {})
    backtester = Backtester(
        strategy=strategy, 
        data=prepared_data, 
        trading_params=trading_params
    )
    backtester.run()

    # 6. Lưu báo cáo nếu có đường dẫn đầu ra
    if output_path:
        backtester.save_report_to_csv(output_path)

if __name__ == "__main__":
    # Chạy backtest và lưu kết quả vào tệp 'scalping_backtest_report.csv'
    # trong thư mục 'reports'
    run_backtest(start_date_str="2025-08-01", output_path="reports/scalping_backtest_report.csv")