import os
import sys
import glob

# Add the `src` path to allow importing custom modules
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_scalping_data
from m15_filtered_scalping_strategy import M15FilteredScalpingStrategy # Import the new strategy
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
    """Runs a backtest for the M15FilteredScalpingStrategy."""
    print("--- Starting Backtest for M15 Filtered Scalping Strategy ---")

    # 1. Load Configuration
    config = get_config()
    if not config:
        return

    # 2. Load Data for M1, M5, M15
    print("Loading data for M1, M5, M15...")
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
        if df is None: return
        timeframes_data[tf] = df

    # 3. Prepare Data
    strategy_params = config.get('strategy', {}).get('M15FilteredScalpingStrategy', {})
    prepared_data = prepare_scalping_data(timeframes_data, strategy_params)

    if prepared_data is None or prepared_data.empty:
        print("Lỗi: Chuẩn bị dữ liệu thất bại hoặc dữ liệu trống.")
        return

    if start_date_str:
        prepared_data = prepared_data[prepared_data.index >= start_date_str]

    # 4. Initialize Strategy, Backtester and Run
    strategy = M15FilteredScalpingStrategy(strategy_params)
    trading_params = config.get('trading', {})
    backtester = Backtester(strategy=strategy, data=prepared_data, trading_params=trading_params)
    backtester.run()

    # 5. Save Report
    if output_path:
        backtester.save_report_to_csv(output_path)

if __name__ == "__main__":
    run_backtest(start_date_str="2025-10-01", output_path="reports/m15_filtered_scalping_report.csv")