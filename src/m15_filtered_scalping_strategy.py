from strategies import BaseStrategy
from combined_strategy import CombinedScalpingStrategy
import pandas as pd


class M15FilteredScalpingStrategy(BaseStrategy):
    """
    Một chiến lược bao bọc (wrapper) để lọc các tín hiệu scalping từ CombinedScalpingStrategy
    dựa trên sức mạnh xu hướng của biểu đồ M15.

    Xu hướng M15 được coi là đủ mạnh nếu khoảng cách giữa
    EMA 34 và EMA 89 lớn hơn một ngưỡng đã định cấu hình.

    Nó cũng kiểm tra sự đồng thuận của xu hướng: đối với tín hiệu MUA, cả hai EMA M15
    phải nằm trên EMA 200 M15. Đối với tín hiệu BÁN, chúng phải nằm dưới.
    """
    def __init__(self, params):
        """
        Khởi tạo M15FilteredScalpingStrategy.

        Args:
            params (dict): Một từ điển chứa các tham số.
                - 'm15_ema_strength_threshold' (float): Chênh lệch giá tối thiểu
                  (ví dụ: tính bằng đô la) giữa EMA 34 và 89 của M15 để coi là xu hướng mạnh.
                - Nó cũng cần các tham số cho CombinedScalpingStrategy bên dưới.
        """
        super().__init__(params)
        self.m15_ema_strength_threshold = params.get('m15_ema_strength_threshold', 0.5)
        # Khởi tạo chiến lược scalping kết hợp bên dưới
        self.combined_scalping_strategy = CombinedScalpingStrategy(params)

    def get_signal(self, analyzed_data: pd.DataFrame):
        """
        Kiểm tra sức mạnh và sự đồng thuận của xu hướng M15, sau đó lấy tín hiệu từ chiến lược kết hợp.
        """
        latest = analyzed_data.iloc[-1]

        # --- 1. Lấy tín hiệu từ chiến lược scalping cơ sở trước ---
        scalping_signal, sl, tp = self.combined_scalping_strategy.get_signal(analyzed_data)

        # Nếu không có tín hiệu scalping, không cần kiểm tra các bộ lọc
        if scalping_signal == 0:
            return 0, None, None

        # --- 2. Áp dụng các bộ lọc xu hướng M15 ---
        m15_ema_34 = latest.get('M15_EMA_34')
        m15_ema_89 = latest.get('M15_EMA_89')
        m15_trend_ema200 = latest.get('M15_TREND_EMA200', 0)

        if m15_ema_34 is None or m15_ema_89 is None:
            return 0, None, None

        # Bộ lọc 1: Sức mạnh xu hướng (khoảng cách tuyệt đối giữa các đường EMA)
        ema_distance = abs(m15_ema_34 - m15_ema_89)
        if ema_distance < self.m15_ema_strength_threshold:
            return 0, None, None # Xu hướng không đủ mạnh

        # Bộ lọc 2: Đồng thuận xu hướng (EMA ngắn, trung và dài hạn)
        is_m15_uptrend = (m15_ema_34 > m15_ema_89) and (m15_trend_ema200 == 1)
        is_m15_downtrend = (m15_ema_34 < m15_ema_89) and (m15_trend_ema200 == -1)

        if (scalping_signal == 1 and not is_m15_uptrend) or \
           (scalping_signal == -1 and not is_m15_downtrend):
            return 0, None, None # Tín hiệu không đồng thuận với xu hướng M15 rõ ràng

        # Nếu tất cả các bộ lọc đều qua, trả về tín hiệu ban đầu
        print(f"Tín hiệu Scalping được M15 Filter xác nhận: {scalping_signal}")
        return scalping_signal, sl, tp