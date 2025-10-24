import os
import sys
import glob

# Thêm đường dẫn `src` để có thể import các module tùy chỉnh
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(project_root, 'src'))

from config_manager import get_config
from data_loader import load_csv_data
from analysis import prepare_analysis_data, prepare_scalping_data
from backtester import Backtester

# Import tất cả các lớp chiến thuật có sẵn
from strategies import (
    MultiTimeframeEmaStrategy,
    MultiTimeframeEmaFibStrategy,
    PriceActionSRStrategy,
    ScalpingEmaCrossoverStrategy,
    ScalpingRsiPullbackStrategy,
    SupplyDemandStrategy,
    MultiEmaPAStochStrategy
)
from combined_strategy import CombinedScalpingStrategy

# Ánh xạ tên chiến thuật trong config với lớp Python tương ứng
STRATEGY_MAP = {
    "MultiTimeframeEmaStrategy": MultiTimeframeEmaStrategy,
    "MultiEmaPAStochStrategy": MultiEmaPAStochStrategy,
    "MultiTimeframeEmaFibStrategy": MultiTimeframeEmaFibStrategy,
    "PriceActionSRStrategy": PriceActionSRStrategy,
    "ScalpingEmaCrossoverStrategy": ScalpingEmaCrossoverStrategy,
    "ScalpingRsiPullbackStrategy": ScalpingRsiPullbackStrategy,
    "SupplyDemandStrategy": SupplyDemandStrategy,
    "CombinedScalpingStrategy": CombinedScalpingStrategy,
}

def find_latest_file(pattern):
    """Tìm file được chỉnh sửa gần đây nhất khớp với một mẫu."""
    try:
        list_of_files = glob.glob(pattern)
        if not list_of_files:
            return None
        return max(list_of_files, key=os.path.getctime)
    except Exception:
        return None

def run_backtest(start_date_str=None, output_path_prefix="reports/"):
    """
    Chạy backtest cho chiến thuật đang được kích hoạt trong file config.
    """
    print("--- Bắt đầu Backtest Động ---")

    # 1. Tải cấu hình
    config = get_config()
    if not config:
        return

    strategy_config = config.get('strategy', {})
    trading_params = config.get('trading', {})

    # 2. Lấy chiến thuật đang kích hoạt và các tham số của nó
    active_strategy_name = strategy_config.get('active_strategy')
    if not active_strategy_name:
        print("Lỗi: 'active_strategy' không được định nghĩa trong mục 'strategy' của config.")
        return

    strategy_params = strategy_config.get(active_strategy_name, {})
    print(f"--- Chiến thuật đang chạy: {active_strategy_name} ---")

    # 3. Chọn lớp chiến thuật từ bản đồ
    StrategyClass = STRATEGY_MAP.get(active_strategy_name)
    if not StrategyClass:
        print(f"Lỗi: Lớp chiến thuật cho '{active_strategy_name}' không tồn tại trong STRATEGY_MAP.")
        return

    # 4. Tải và chuẩn bị dữ liệu dựa trên loại chiến thuật
    print("Đang tải và chuẩn bị dữ liệu...")
    data_dir = os.path.join(project_root, 'Data')
    
    # Heuristic: Các chiến thuật "Scalping" hoặc "Combined" sử dụng dữ liệu scalping
    if "Scalping" in active_strategy_name or "Combined" in active_strategy_name:
        timeframe_patterns = {
            'm1': os.path.join(data_dir, 'XAUUSD_M1_*.csv'),
            'm5': os.path.join(data_dir, 'XAUUSD_M5_*.csv'),
            'm15': os.path.join(data_dir, 'XAUUSD_M15_*.csv'),
        }
        timeframes_data = {}
        for tf, pattern in timeframe_patterns.items():
            latest_file = find_latest_file(pattern)
            if not latest_file:
                print(f"Lỗi: Không tìm thấy file dữ liệu cho khung thời gian {tf.upper()}")
                return
            df = load_csv_data(latest_file)
            if df is None: return
            timeframes_data[tf] = df
        
        prepared_data = prepare_scalping_data(timeframes_data, strategy_params)
    else:
        # Tải dữ liệu cho các chiến thuật đa khung thời gian chung
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
                print(f"Cảnh báo: Không tìm thấy file dữ liệu cho {tf.upper()}. Bỏ qua.")
                continue
            df = load_csv_data(latest_file)
            if df is None: return
            timeframes_data[tf] = df

        sr_periods = strategy_params.get('sr_periods', {'m15': 200, 'h1': 50, 'h4': 50})
        include_sd = "SupplyDemand" in active_strategy_name
        prepared_data = prepare_analysis_data(timeframes_data, sr_periods, include_sd_zones=include_sd)

    if prepared_data is None or prepared_data.empty:
        print("Lỗi: Chuẩn bị dữ liệu thất bại hoặc dữ liệu trống.")
        return

    if start_date_str:
        print(f"Lọc dữ liệu từ ngày: {start_date_str}")
        prepared_data = prepared_data[prepared_data.index >= start_date_str]

    # 5. Khởi tạo chiến thuật
    strategy = StrategyClass(strategy_params)

    # 6. Khởi tạo và chạy Backtester
    backtester = Backtester(strategy=strategy, data=prepared_data, trading_params=trading_params)
    backtester.run()

    # 7. Lưu báo cáo
    output_filename = os.path.join(output_path_prefix, f"{active_strategy_name}_report.csv")
    backtester.save_report_to_csv(output_filename)
    print(f"--- Backtest hoàn tất. Báo cáo đã được lưu tại: {output_filename} ---")

if __name__ == "__main__":
    run_backtest(start_date_str="2025-10-01", output_path_prefix="reports/MultiTimeframeEmaStrategy_report.csv")
