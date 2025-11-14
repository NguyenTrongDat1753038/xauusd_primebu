# -*- coding: utf-8 -*-
import pandas as pd
import os
import itertools
from tqdm import tqdm

# Import project components
from data_loader import load_csv_data
from analysis import prepare_analysis_data
from strategies import MultiTimeframeEmaStrategy
from backtester import Backtester

def run_optimizer():
    """
    Runs an optimization process to find the best parameters for a strategy.
    """
    print("="*50)
    print("== STRATEGY PARAMETER OPTIMIZATION ==")
    print("="*50 + "\n")

    # --- 1. Define Parameter Grid ---
    # Define the range of values for each parameter you want to optimize
    param_grid = {
        'adx_threshold': [20, 25, 30],               # Ngưỡng ADX để xác định xu hướng
        'volatility_threshold': [1.3, 1.5, 1.7],     # Ngưỡng biến động
        'atr_sl_multiplier': [1.5, 2.0, 2.5],        # Hệ số nhân ATR cho SL lúc bình thường
        'atr_sl_multiplier_high_vol': [2.5, 3.0, 3.5] # Hệ số nhân ATR cho SL lúc biến động cao
    }
    
    # We will keep the TP multiplier proportional to the SL multiplier (R:R = 1:2)
    # So, atr_tp_multiplier = atr_sl_multiplier * 2
    # and atr_tp_multiplier_high_vol = atr_sl_multiplier_high_vol * 2

    print("Parameter Grid to be tested:")
    for param, values in param_grid.items():
        print(f"- {param}: {values}")

    # Create all possible combinations of parameters
    keys, values = zip(*param_grid.items())
    param_combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]
    
    print(f"\nTotal combinations to test: {len(param_combinations)}\n")


    # --- 2. Load and Prepare Data (do this only once) ---
    print("Loading and preparing data once for all backtests...")
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
    required_files = {
        'm15': 'XAUUSD_M15_20210101_20251023.csv',
        'm30': 'XAUUSD_M30_20210101_20251023.csv',
        'h1': 'XAUUSD_H1_20210101_20251023.csv',
        'h4': 'XAUUSD_H4_20210101_20251023.csv',
    }
    timeframes_data = {}
    for tf, filename in required_files.items():
        file_path = os.path.abspath(os.path.join(data_dir, filename))
        df = load_csv_data(file_path)
        if df is None:
            print(f"Fatal Error: Could not load data file {filename}.")
            return
        timeframes_data[tf] = df

    start_date = "2024-01-01"
    end_date = "2024-06-01"
    base_tf_key = 'm15'
    timeframes_data[base_tf_key] = timeframes_data[base_tf_key].loc[start_date:end_date]
    
    sr_periods_config = {"m15": 200, "h1": 50, "h4": 50}
    analysis_data = prepare_analysis_data(timeframes_data, sr_periods=sr_periods_config)
    
    if analysis_data is None or analysis_data.empty:
        print("Fatal Error: Data preparation failed.")
        return
    print("Data preparation complete.\n")


    # --- 3. Run Optimization Loop ---
    all_results = []
    
    # Using tqdm for a progress bar
    for params in tqdm(param_combinations, desc="Optimizing Parameters"):
        
        # Add proportional TP multipliers
        params['atr_tp_multiplier'] = params['atr_sl_multiplier'] * 2
        params['atr_tp_multiplier_high_vol'] = params['atr_sl_multiplier_high_vol'] * 2
        params['use_volatility_filter'] = True # Ensure it's enabled

        # Initialize strategy with the current parameter combination
        strategy = MultiTimeframeEmaStrategy(params)
        
        # Basic trading params for the backtester
        trading_params = {
            "initial_balance": 10000,
            "use_dynamic_sizing": True,
            "risk_per_trade": 0.01,
            "point_value": 1.0,
            "use_breakeven_stop": True,
            "breakeven_trigger_points": 10.0,
            "breakeven_extra_points": 0.5,
        }

        # Run backtest with verbose=False to keep output clean
        backtester = Backtester(strategy=strategy, data=analysis_data, trading_params=trading_params, verbose=False)
        backtester.run()
        
        # Get results and store them
        run_result = backtester.get_results()
        
        # Combine params and results
        full_run_details = {**params, **run_result}
        all_results.append(full_run_details)

    # --- 4. Analyze and Display Top Results ---
    if not all_results:
        print("Optimization run did not produce any results.")
        return

    results_df = pd.DataFrame(all_results)
    
    # Sort by Final Balance in descending order
    top_results = results_df.sort_values(by='final_balance', ascending=False).head(5)

    print("\n" + "="*80)
    print("== OPTIMIZATION COMPLETE: TOP 5 BEST PARAMETER SETS ==")
    print("="*80)
    
    # Define columns to display
    display_cols = [
        'final_balance', 'total_pnl_currency', 'win_rate', 'total_trades',
        'adx_threshold', 'volatility_threshold', 
        'atr_sl_multiplier', 'atr_sl_multiplier_high_vol'
    ]
    
    # Reorder and format for better readability
    top_results_display = top_results[display_cols]
    top_results_display = top_results_display.round(2)

    # Set display options for better console output
    pd.set_option('display.width', 1000)
    pd.set_option('display.max_columns', 10)

    print(top_results_display.to_string())
    print("\n" + "="*80)


if __name__ == "__main__":
    run_optimizer()
