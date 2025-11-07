import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os

def plot_performance_charts_weekly(initial_balance=10000):
    """
    Tải kết quả backtest và vẽ biểu đồ Equity Curve và PnL hàng tuần.
    """

    # --- 1. Tải dữ liệu ---
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    results_file = os.path.join(project_root, 'reports', 'backtest_results_TEST.csv')

    if not os.path.exists(results_file):
        print(f"Lỗi: Không tìm thấy file kết quả tại '{results_file}'")
        print("Vui lòng chạy backtest trước để tạo file kết quả.")
        return

    try:
        df = pd.read_csv(results_file)
        if df.empty:
            print("File kết quả trống. Không có dữ liệu để vẽ biểu đồ.")
            return
    except Exception as e:
        print(f"Lỗi khi đọc file CSV: {e}")
        return

    # --- 2. Chuẩn bị dữ liệu ---
    pnl_column_name = 'pnl_currency'

    df['exit_time'] = pd.to_datetime(df['exit_time'], errors='coerce')
    df.dropna(subset=['exit_time', pnl_column_name], inplace=True)

    if df.empty:
        print("Không có dữ liệu hợp lệ sau khi làm sạch. Dừng lại.")
        return

    df.set_index('exit_time', inplace=True)

    # --- 3a. Tính toán và vẽ Equity Curve ---
    df['equity'] = df[pnl_column_name].cumsum() + initial_balance

    plt.style.use('seaborn-v0_8-darkgrid')
    fig, axes = plt.subplots(2, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle('Phân Tích Hiệu Suất Backtest (Theo Tuần)', fontsize=18, fontweight='bold')

    # Biểu đồ Equity Curve
    axes[0].plot(df.index, df['equity'], label='Equity Curve', color='dodgerblue', linewidth=2)
    
    # Tính toán và vẽ Drawdown
    running_max = df['equity'].cummax()
    drawdown = (df['equity'] - running_max) / running_max
    max_drawdown = drawdown.min()
    
    axes[0].fill_between(drawdown.index, df['equity'], running_max, facecolor='red', alpha=0.3, label=f'Drawdown (Max: {max_drawdown:.2%})')
    axes[0].set_title('Đường Cong Vốn (Equity Curve) và Sụt Giảm (Drawdown)', fontsize=14)
    axes[0].set_ylabel('Vốn (USD)', fontsize=12)
    axes[0].legend()
    axes[0].grid(True)

    # --- 3b. Nhóm theo tuần và tính tổng PnL ---
    weekly_pnl = df[pnl_column_name].resample('W-MON').sum()

    if not weekly_pnl.empty:
        colors = ['#2ca02c' if x >= 0 else '#d62728' for x in weekly_pnl]
        weekly_pnl.plot(kind='bar', ax=axes[1], color=colors, width=0.8)
        axes[1].set_title('Tổng Lợi Nhuận (PnL) Hàng Tuần', fontsize=14)
        axes[1].set_xlabel('Tuần', fontsize=12)
        axes[1].set_ylabel('Lợi nhuận (USD)', fontsize=12)
        axes[1].axhline(0, color='black', linewidth=0.8)
        axes[1].set_xticklabels([d.strftime('%Y-%m-%d') for d in weekly_pnl.index], rotation=45, ha='right')

        for bar in axes[1].patches:
            height = bar.get_height()
            label = f'${height:,.0f}'
            x_pos = bar.get_x() + bar.get_width() / 2
            y_pos = height + (30 if height >= 0 else -30)
            va = 'bottom' if height >= 0 else 'top'
            axes[1].text(x_pos, y_pos, label, ha='center', va=va, fontsize=9, color='dimgray')

    plt.tight_layout()
    fig.subplots_adjust(top=0.93)

    # --- 6. Lưu và hiển thị ---
    output_path = os.path.join(project_root, 'reports', 'performance_charts_weekly.png')
    try:
        plt.savefig(output_path, dpi=150)
        print(f"Biểu đồ đã được lưu tại: {output_path}")
    except Exception as e:
        print(f"Lỗi khi lưu biểu đồ: {e}")

    plt.show()

if __name__ == "__main__":
    plot_performance_charts_weekly(initial_balance=10000)