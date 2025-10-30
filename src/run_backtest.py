import pandas as pd
import os
import pandas_ta as ta

from data_loader import load_csv_data
from config_manager import get_config
from analysis import prepare_scalping_data
from backtester import Backtester
from m15_filtered_scalping_strategy import M15FilteredScalpingStrategy

def run_final_backtest():
    """
    Runs a single backtest with the BEST parameters found during optimization.
    """
    print("="*50)
    print("== RUNNING BACKTEST FOR FINAL OPTIMIZED STRATEGY ==")
    print("== Strategy: M15FilteredScalpingStrategy ==")
    print("="*50 + "\n")

    config = get_config()
    if not config:
        print("Không thể tải cấu hình. Dừng backtest.")
        return

    # --- 1. Load Data ---
    # Construct an absolute path to the data directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data_dir = os.path.join(project_root, 'data')

    backtest_symbol = config.get('trading', {}).get('backtest_symbol', 'XAUUSDm')
    
    required_files = {
        'm1': f'{backtest_symbol}_M1_202301022301_202510301643.csv',
        'm5': f'{backtest_symbol}_M5_202301022300_202510301640.csv',
        'm15': f'{backtest_symbol}_M15_202301022300_202510301630.csv',
        'm30': f'{backtest_symbol}_M30_202301022300_202510301630.csv',
        'h1': f'{backtest_symbol}_H1_202301022300_202510301600.csv'
        #'h4': f'{backtest_symbol}_H4_202301030000_202510281600.csv',
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
        # --- DEBUGGING: Verify loaded data ---
        if not isinstance(df.index, pd.DatetimeIndex):
            print(f"DEBUG: Index for {tf} is not DatetimeIndex. Type: {type(df.index)}")
            return # Stop if index is not correct
        if not df.index.is_monotonic_increasing:
            print(f"DEBUG: Index for {tf} is not sorted. First: {df.index[0]}, Last: {df.index[-1]}")
            return # Stop if index is not sorted

    # --- 2. Filter Data by Date ---
    start_date = "2025-05-01"
    end_date = "2025-10-30"
    
    print(f"Filtering data from {start_date} to {end_date}...")
    # LỌC TẤT CẢ CÁC KHUNG THỜI GIAN, KHÔNG CHỈ M1
    for tf in timeframes_data:
        timeframes_data[tf] = timeframes_data[tf].loc[start_date:end_date]
    
    if timeframes_data['m1'].empty:
        print("No data available for the selected date range in the base timeframe (M1).")
        return

    # --- 4. Initialize and Run Backtester with OPTIMIZED parameters ---
    print("Initializing strategy and backtester with OPTIMIZED parameters...")

    # Load parameters from config file for consistency
    strategy_params = config.get('strategy', {}).get('M15FilteredScalpingStrategy', {})
    trading_params = config.get('trading', {})

    if not strategy_params or not trading_params:
        print("Error: Strategy or trading parameters are missing in config.json")
        return

    strategy = M15FilteredScalpingStrategy(strategy_params)

    # --- 3. Prepare and Analyze Data ---
    print("Preparing data and calculating indicators for scalping strategy...")
    analysis_data = prepare_scalping_data(timeframes_data, config.get('strategy', {}))
    if analysis_data is None or analysis_data.empty:
        print("Error during data preparation.")
        # --- DEBUGGING: Print info about analysis_data if it's empty ---
        if analysis_data is not None:
            print(f"DEBUG: analysis_data is empty. Shape: {analysis_data.shape}")
            print(f"DEBUG: NaNs in analysis_data before final check:\n{analysis_data.isnull().sum()}")
        return

    # Run with verbose=True to see the final report clearly
    backtester = Backtester(strategy=strategy, data=analysis_data, trading_params=trading_params, verbose=True)
    
    print("\n" + "="*20 + " STARTING FINAL BACKTEST " + "="*20)
    backtester.run()
    print("="*20 + " FINAL BACKTEST FINISHED " + "="*20)

    # --- Save report to 'reports' folder ---
    reports_dir = os.path.join(project_root, 'reports')
    os.makedirs(reports_dir, exist_ok=True) # Tạo thư mục nếu nó chưa tồn tại

    output_file = os.path.join(reports_dir, "backtest_results_OPTIMIZED.csv")
    backtester.save_report_to_csv(output_file)
    print(f"Detailed optimized results saved to: {output_file}")

if __name__ == "__main__":
    run_final_backtest()
