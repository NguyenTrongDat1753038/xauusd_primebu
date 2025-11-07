import pandas as pd
import os
import sys

# Thêm thư mục gốc của dự án vào sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from src.data_loader import load_csv_data
from src.config_manager import get_config_for_env
from src.analysis import prepare_scalping_data
from src.backtester import Backtester
from src.cpr_volume_profile_strategy import CprVolumeProfileStrategy
from src.advanced_ema_strategy import AdvancedEmaStrategy
from src.ema_bounce_strategy import EmaBounceStrategy

def run_final_backtest():
    """
    Chạy một backtest duy nhất với cấu hình từ môi trường testing.
    """
    print("="*50)
    print("== RUNNING BACKTEST FOR TESTING ENVIRONMENT ==")
    print("="*50 + "\n")

    config = get_config_for_env('testing')
    if not config:
        print("Không thể tải cấu hình. Dừng backtest.")
        return

    # --- 1. Load Data ---
    data_dir = os.path.join(project_root, 'data')

    backtest_symbol = config.get('trading', {}).get('backtest_symbol', 'XAUUSDm')
    
    required_files = {
        'm1': f'{backtest_symbol}_M1_202301022301_202510312057.csv',
        'm5': f'{backtest_symbol}_M5_202301022300_202510312055.csv',
        'm15': f'{backtest_symbol}_M15_202301022300_202510312045.csv',
        'm30': f'{backtest_symbol}_M30_202301022300_202510312030.csv',
        'h1': f'{backtest_symbol}_H1_202301022300_202510312000.csv',
        'h4': f'{backtest_symbol}_H4_202301022000_202510312000.csv',
        'd1': f'{backtest_symbol}_D1_202301020000_202510310000.csv',
    }

    timeframes_data = {}
    print("Loading historical data...")
    for tf, filename in required_files.items():
        file_path = os.path.join(data_dir, filename) # data_dir is now absolute
        df = load_csv_data(file_path)
        if df is None:
            print(f"Error: Could not load file {filename}. Please check the path: {file_path}")
            return
        timeframes_data[tf] = df

    # --- 2. Filter Data by Date ---
    start_date = "2025-10-01"
    end_date = "2025-10-31"
    
    print(f"Filtering data from {start_date} to {end_date}...")
    # LỌC TẤT CẢ CÁC KHUNG THỜI GIAN, KHÔNG CHỈ M1
    for tf in timeframes_data:
        timeframes_data[tf] = timeframes_data[tf].loc[start_date:end_date]
    
    if timeframes_data['m15'].empty:
        print("No data available for the selected date range in the base timeframe (M1).")
        return

    # --- 4. Initialize and Run Backtester ---
    print("Initializing strategy and backtester...")

    # Load parameters from config file for consistency
    strategy_config = config.get('strategy', {})
    trading_params = config.get('trading', {})

    if not strategy_config or not trading_params:
        print("Error: Strategy or trading parameters are missing in config.json")
        return

    # --- Logic lựa chọn chiến lược động ---
    active_strategy_name = strategy_config.get('active_strategy', 'CprVolumeProfileStrategy')
    
    strategy = None
    if active_strategy_name == 'CprVolumeProfileStrategy':
        strategy = CprVolumeProfileStrategy(strategy_config.get('CprVolumeProfileStrategy', {}))
    elif active_strategy_name == 'AdvancedEmaStrategy':
        strategy = AdvancedEmaStrategy(strategy_config.get('AdvancedEmaStrategy', {}))
    elif active_strategy_name == 'EmaBounceStrategy':
        strategy = EmaBounceStrategy(strategy_config.get('EmaBounceStrategy', {}))
    else:
        print(f"Error: Active strategy '{active_strategy_name}' is not supported for backtesting in this script.")
        return


    print(f"== Active Strategy for Backtest: {active_strategy_name} ==")
    
    # --- 3. Prepare and Analyze Data ---
    print("Preparing data and calculating indicators...")
    analysis_data = prepare_scalping_data(timeframes_data, config.get('strategy', {}))
    if analysis_data is None or analysis_data.empty:
        print("Error during data preparation.")
        return

    backtester = Backtester(strategy=strategy, data=analysis_data, trading_params=trading_params, verbose=True)
    
    print("\n" + "="*20 + " STARTING BACKTEST " + "="*20)
    backtester.run()
    print("="*20 + " BACKTEST FINISHED " + "="*20)

    # --- Save report to 'reports' folder ---
    reports_dir = os.path.join(project_root, 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    output_file = os.path.join(reports_dir, "backtest_results_TEST.csv")
    backtester.save_report_to_csv(output_file)
    print(f"Detailed test results saved to: {output_file}")

if __name__ == "__main__":
    run_final_backtest()