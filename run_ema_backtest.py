import os
import sys
import glob

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_analysis_data
from strategies import MultiTimeframeEmaStrategy # Use the original EMA strategy
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
    """Chạy backtest cho chiến lược MultiTimeframeEmaStrategy."""
    print("--- Bắt đầu Backtest cho Chiến lược Multi-Timeframe EMA ---")

    # 1. Tải cấu hình
    config = get_config()
    if not config:
        return

    # 2. Tải dữ liệu (giống với chiến lược Cung/Cầu)
    print("Đang tải dữ liệu...")
    data_dir = os.path.join(project_root, 'Data')
    
    # Tự động tìm các tệp dữ liệu mới nhất
    timeframe_patterns = {
        'm15': os.path.join(data_dir, 'XAUUSD_M15_*.csv'),
        'm30': os.path.join(data_dir, 'XAUUSD_M30_*.csv'),
        'h1': os.path.join(data_dir, 'XAUUSD_H1_*.csv'),
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

    # 3. Chuẩn bị dữ liệu
    strategy_params = config.get('strategy', {}).get('MultiTimeframeEmaStrategy', {})
    sr_periods = strategy_params.get('sr_periods', {'m15': 200, 'h1': 50, 'h4': 50})
    # Gọi hàm mà không cần tính toán S/D zones
    prepared_data = prepare_analysis_data(timeframes_data, sr_periods, include_sd_zones=False)
    
    if prepared_data is None or prepared_data.empty:
        return

    # 4. Khởi tạo chiến lược
    strategy = MultiTimeframeEmaStrategy(strategy_params)

    # 5. Khởi tạo và chạy Backtester
    trading_params = config.get('trading', {})
    backtester = Backtester(strategy=strategy, data=prepared_data, trading_params=trading_params)
    backtester.run()

    # 6. Lưu báo cáo
    if output_path:
        backtester.save_report_to_csv(output_path)

if __name__ == "__main__":
    run_backtest(output_path="reports/ema_backtest_report.csv")