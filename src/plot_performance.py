import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

def plot_weekly_pnl():
    """
    Tải kết quả backtest và vẽ biểu đồ Lợi nhuận/Thua lỗ (PnL) hàng tuần.
    """
    print("--- Đang tạo biểu đồ PnL hàng tuần ---")

    # --- 1. Tải dữ liệu ---
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    results_file = os.path.join(project_root, 'reports', 'backtest_results_OPTIMIZED.csv')

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
    # Chuyển đổi cột thời gian và xử lý lỗi nếu có
    # Sửa lỗi: Sử dụng cột 'pnl' thay vì 'pnl_currency' không tồn tại
    pnl_column_name = 'pnl_currency' # Tên cột lợi nhuận thực tế trong file CSV

    df['exit_time'] = pd.to_datetime(df['exit_time'], errors='coerce')
    df.dropna(subset=['exit_time', pnl_column_name], inplace=True)

    if df.empty:
        print("Không có dữ liệu hợp lệ sau khi làm sạch. Dừng lại.")
        return

    df.set_index('exit_time', inplace=True)

    # --- 3. Nhóm theo tuần và tính tổng PnL ---
    # 'W-MON' nhóm các tuần bắt đầu từ thứ Hai
    weekly_pnl = df[pnl_column_name].resample('W-MON').sum()

    if weekly_pnl.empty:
        print("Không có giao dịch nào để tổng hợp theo tuần.")
        return

    # --- 4. Vẽ biểu đồ ---
    plt.style.use('seaborn-v0_8-darkgrid') # Sử dụng style cho đẹp hơn
    fig, ax = plt.subplots(figsize=(15, 8))

    # Vẽ các cột màu xanh cho tuần lãi, màu đỏ cho tuần lỗ
    colors = ['#2ca02c' if x >= 0 else '#d62728' for x in weekly_pnl]
    weekly_pnl.plot(kind='bar', ax=ax, color=colors, width=0.8)

    # --- 5. Định dạng biểu đồ ---
    ax.set_title('Tổng Lợi Nhuận (PnL) Hàng Tuần', fontsize=16, fontweight='bold')
    ax.set_xlabel('Tuần', fontsize=12)
    ax.set_ylabel('Lợi nhuận (USD)', fontsize=12)
    ax.axhline(0, color='black', linewidth=0.8) # Đường zero line

    # Định dạng trục x để hiển thị ngày tháng dễ đọc hơn
    ax.set_xticklabels([d.strftime('%Y-%m-%d') for d in weekly_pnl.index], rotation=45, ha='right')
    
    plt.tight_layout() # Tự động điều chỉnh cho vừa vặn

    # --- 6. Lưu và hiển thị ---
    output_path = os.path.join(project_root, 'reports', 'weekly_pnl_chart.png')
    try:
        plt.savefig(output_path, dpi=150)
        print(f"Biểu đồ đã được lưu tại: {output_path}")
    except Exception as e:
        print(f"Lỗi khi lưu biểu đồ: {e}")

    plt.show()


if __name__ == "__main__":
    plot_weekly_pnl()