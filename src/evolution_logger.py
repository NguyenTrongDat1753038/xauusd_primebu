import json
import os
from datetime import datetime

LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'reports', 'evolution_log.jsonl')

def log_trade_context(trade_signal: int, sl: float, tp: float, latest_bar: dict, session_name: str, session_multiplier: float):
    """
    Ghi lại bối cảnh thị trường đầy đủ tại thời điểm một tín hiệu giao dịch được tạo ra.

    Args:
        trade_signal (int): Tín hiệu giao dịch (1 cho BUY, -1 cho SELL).
        sl (float): Mức Stop Loss được tính toán.
        tp (float): Mức Take Profit được tính toán.
        latest_bar (dict): Dòng dữ liệu cuối cùng từ DataFrame phân tích, chứa tất cả các chỉ báo.
        session_name (str): Tên của phiên giao dịch hiện tại.
        session_multiplier (float): Hệ số rủi ro của phiên hiện tại.
    """
    try:
        # Các chỉ báo chính cần ghi lại để phân tích
        key_indicators = [
            'M15_TREND_EMA200', 'H1_TREND', 'H4_TREND',
            'ADX_14_M15', 'RSI_14', 'ATR_14_M5',
            'M5_EMA_9', 'M5_EMA_20',
            'M15_EMA_34', 'M15_EMA_89',
            'H1_EMA_34', 'H1_EMA_89',
            'BBU_20_2.0', 'BBL_20_2.0', 'BBM_20_2.0', 'BBB_20_2.0', 'BBP_20_2.0'
        ]

        context = {indicator: latest_bar.get(indicator) for indicator in key_indicators}

        # Tìm và ghi lại tất cả các mô hình nến đang hoạt động
        active_patterns = {
            col: int(latest_bar[col])
            for col in latest_bar.keys() # Sửa: Dùng .keys() cho dict thay vì .index
            if col.startswith('CDL_') and latest_bar[col] != 0
        }
        context['active_patterns'] = active_patterns

        # Tạo bản ghi hoàn chỉnh
        log_entry = {
            'timestamp_utc': datetime.utcnow().isoformat(),
            'signal_time': latest_bar.get('time', datetime.utcnow().isoformat()), # Sửa: Lấy thời gian từ dict, nếu không có thì dùng thời gian hiện tại
            'trade_type': 'BUY' if trade_signal == 1 else 'SELL',
            'calculated_sl': sl,
            'calculated_tp': tp,
            'session_info': {
                'name': session_name,
                'multiplier': session_multiplier
            },
            'market_context': context
        }

        # Ghi vào file log dưới dạng JSON Lines (mỗi dòng một JSON)
        with open(LOG_FILE_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, default=str) + '\n') # Dùng default=str để xử lý các kiểu dữ liệu không tuần tự hóa được

        print(f"[*] Đã ghi lại bối cảnh cho tín hiệu {log_entry['trade_type']} vào evolution_log.jsonl")

    except Exception as e:
        print(f"[LỖI] Không thể ghi lại bối cảnh giao dịch: {e}")