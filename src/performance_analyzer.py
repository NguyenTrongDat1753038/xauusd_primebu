import pandas as pd
import os

def analyze_performance():
    """
    Analyzes the results of a backtest from a CSV file.
    """
    # --- 1. Load Data ---
    results_file = 'backtest_results_dynamic_sizing.csv'
    
    # Check if file exists
    if not os.path.exists(results_file):
        print(f"Error: Results file not found at '{results_file}'")
        print("Please run the backtest first to generate the results file.")
        return

    print(f"Analyzing backtest results from '{results_file}'...")
    df = pd.read_csv(results_file)

    # --- 2. Data Preparation ---
    # Convert time columns to datetime objects
    df['entry_time'] = pd.to_datetime(df['entry_time'])
    df['exit_time'] = pd.to_datetime(df['exit_time'])

    # Extract time components for grouping
    df['entry_hour'] = df['entry_time'].dt.hour
    df['entry_weekday'] = df['entry_time'].dt.day_name()

    # --- 3. Perform Analysis ---

    # PnL by Hour of Day
    pnl_by_hour = df.groupby('entry_hour')['pnl_currency'].sum()

    # PnL by Weekday
    # Order the days of the week correctly
    weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    pnl_by_weekday = df.groupby('entry_weekday')['pnl_currency'].sum().reindex(weekday_order).dropna()

    # Analysis of Breakeven Trades
    breakeven_trades = df[df['breakeven_applied'] == True]
    breakeven_win_count = len(breakeven_trades[breakeven_trades['pnl_currency'] > 0])
    breakeven_loss_count = len(breakeven_trades[breakeven_trades['pnl_currency'] <= 0])


    # --- 4. Display Results ---
    print("\n" + "="*50)
    print("== PERFORMANCE ANALYSIS REPORT ==")
    print("="*50)

    print("\n--- Profit/Loss by Hour of Day (Entry Time) ---")
    print(pnl_by_hour.to_string())

    print("\n--- Profit/Loss by Day of Week (Entry Time) ---")
    print(pnl_by_weekday.to_string())
    
    print("\n--- Breakeven Stop Analysis ---")
    print(f"Total trades where breakeven was applied: {len(breakeven_trades)}")
    print(f"  - Trades closed in profit (or at BE): {breakeven_win_count}")
    print(f"  - Trades closed in loss (after BE):   {breakeven_loss_count}")


    print("\n" + "="*50)
    print("== END OF REPORT ==")
    print("="*50)


if __name__ == "__main__":
    analyze_performance()
