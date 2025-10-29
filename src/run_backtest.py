import pandas as pd
import os

from data_loader import load_csv_data
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

    # --- 1. Load Data ---
    # Construct an absolute path to the data directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    data_dir = os.path.join(project_root, 'data')
    
    required_files = {
        'm1': 'XAUUSD_M1_202301030101_202510281624.csv', # Assuming this filename
        'm5': 'XAUUSD_M5_202301030100_202510281625.csv', # Assuming this filename
        'm15': 'XAUUSD_M15_202301030100_202510281615.csv',
        #'m30': 'XAUUSD_M30_202301030100_202510281615.csv'
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
    start_date = "2025-06-01"
    end_date = "2025-10-28"
    
    print(f"Filtering data from {start_date} to {end_date}...")
    base_tf_key = 'm1' # Base timeframe for scalping is M1
    timeframes_data[base_tf_key] = timeframes_data[base_tf_key].loc[start_date:end_date]
    
    if timeframes_data[base_tf_key].empty:
        print("No data available for the selected date range.")
        return

    # --- 4. Initialize and Run Backtester with OPTIMIZED parameters ---
    print("Initializing strategy and backtester with OPTIMIZED parameters...")

    # Parameters for M15FilteredScalpingStrategy and its sub-strategies
    strategy_params = {
        "m15_ema_strength_threshold": 0.5, # Min distance between M15 EMAs
        "required_votes": 1, # Need at least 1 signal from sub-strategies
        "ScalpingEmaCrossoverStrategy": {
            "ema_fast_len": 9,
            "ema_slow_len": 20,
            "swing_lookback": 10,
            "rr_ratio": 1.5
        },
        "ScalpingRsiPullbackStrategy": {
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "swing_lookback": 10,
            "rr_ratio": 1.5
        }
    }
    strategy = M15FilteredScalpingStrategy(strategy_params)

    # --- 3. Prepare and Analyze Data ---
    print("Preparing data and calculating indicators for scalping strategy...")
    analysis_data = prepare_scalping_data(timeframes_data, strategy_params)
    if analysis_data is None or analysis_data.empty:
        print("Error during data preparation.")
        return
    
    trading_params = {
        "initial_balance": 10000,
        "max_open_trades": 3, # Scalping usually has 1 trade at a time
        "use_dynamic_sizing": True, # Enable dynamic lot sizing
        "risk_per_trade": 0.03, # Risk 1% of balance per trade
        "contract_size": 100.0, # Contract size for XAUUSD (1 lot = 100 ounces)
        
        # --- Nâng cấp từ Breakeven sang Trailing Stop ---
        # Tắt Breakeven để Trailing Stop hoạt động
        "use_breakeven_stop": False,
        
        # Bật và cấu hình Trailing Stop
        "use_trailing_stop": True,
        "trailing_trigger_step": 10.0, # Cứ mỗi 10 giá lợi nhuận...
        "trailing_profit_step": 5,   # ...thì dời SL lên 5 giá theo hướng lợi nhuận.

        "close_on_friday": True,
        "friday_close_time": "21:30:00"
    }

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
