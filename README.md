# Bot Giao Dịch Tự Động cho MetaTrader 5

Bot này được thiết kế để thực hiện các chiến lược giao dịch một cách tự động trên nền tảng MetaTrader 5 (MT5). Nó có khả năng chạy nhiều chiến lược khác nhau, quản lý rủi ro linh hoạt, và gửi thông báo theo thời gian thực qua Telegram.

## Tính Năng Nổi Bật

- **Tích hợp MetaTrader 5**: Kết nối trực tiếp với tài khoản MT5 để lấy dữ liệu thị trường và thực hiện giao dịch.
- **Hỗ trợ Đa Chiến Lược**: Dễ dàng chuyển đổi giữa các chiến lược giao dịch khác nhau thông qua tệp cấu hình (ví dụ: `M15FilteredScalpingStrategy`, `CprVolumeProfileStrategy`).
- **Quản Lý Rủi Ro Nâng Cao**:
  - Tự động tính toán khối lượng lệnh (lot size) dựa trên phần trăm rủi ro của tài khoản.
  - Giảm thiểu rủi ro khi tài khoản sụt giảm (Drawdown Reducer).
  - Cơ chế ngắt mạch (Circuit Breaker) để dừng giao dịch khi thua lỗ trong ngày hoặc thua lỗ liên tiếp.
- **Quản Lý Lệnh Thông Minh**:
  - Hỗ trợ dời Stop Loss về hòa vốn (Breakeven).
  - Hỗ trợ Trailing Stop theo nhiều bậc (Tiered Trailing Stop).
  - Tự động hủy các lệnh chờ đã tồn tại quá lâu.
- **Thông Báo Qua Telegram**: Gửi thông báo tức thì về trạng thái bot, các lệnh được đặt, cập nhật và đóng.
- **Cấu Hình Linh Hoạt**: Mọi tham số từ thông tin đăng nhập, chiến lược, đến quản lý rủi ro đều có thể được tùy chỉnh thông qua các tệp cấu hình `.json`.
- **Dừng Bot An Toàn**: Cung cấp script `stop_bot.bat` để dừng bot một cách mượt mà, đảm bảo tất cả các lệnh được đóng và hủy đúng cách.

## Yêu Cầu Hệ Thống

- **Hệ điều hành**: Windows (do sử dụng script `.bat` và `wmic`).
- **Python**: Phiên bản 3.10 trở lên.
- **MetaTrader 5**: Cần cài đặt và đăng nhập sẵn vào tài khoản giao dịch.
- **Quyền truy cập mạng**: Để kết nối đến máy chủ MT5 và Telegram.

## Hướng Dẫn Cài Đặt

Thực hiện các bước sau để cài đặt môi trường và chạy bot.

### 1. Cài đặt MetaTrader 5

- Tải và cài đặt phần mềm MetaTrader 5 từ nhà môi giới của bạn (ví dụ: Exness).
- Đăng nhập vào tài khoản giao dịch của bạn.
- Trong MT5, vào menu **Tools -> Options -> Expert Advisors**.
- Đánh dấu vào ô **"Allow algorithmic trading"**.

### 2. Chuẩn bị Môi trường Python

1.  **Tạo Môi trường ảo (Virtual Environment)**: Mở Command Prompt hoặc PowerShell trong thư mục gốc của dự án (`D:\Code\XAU_Bot_Predict`) và chạy lệnh sau để tạo một môi trường ảo có tên là `ta_env`:

    ```bash
    python -m venv ta_env
    ```

2.  **Kích hoạt Môi trường ảo**:

    ```bash
    .\ta_env\Scripts\activate
    ```

    Sau khi kích hoạt, bạn sẽ thấy `(ta_env)` ở đầu dòng lệnh.

### 3. Cài đặt các Thư viện cần thiết

Chạy lệnh sau để cài đặt tất cả các thư viện được liệt kê trong tệp `requirements.txt`.

```bash
pip install -r requirements.txt
```

**Nội dung tệp `requirements.txt` (tạo file này nếu chưa có):**

```
MetaTrader5
pandas
pandas-ta
numpy
setproctitle
python-telegram-bot[job-queue]
```

**Lưu ý quan trọng**: Cần cài đặt `python-telegram-bot` với tùy chọn `[job-queue]` để tính năng thông báo hoạt động chính xác.

## Hướng Dẫn Cấu Hình

Tất cả các cấu hình được quản lý trong thư mục `configs`. Mỗi tệp `.json` (ví dụ: `btcusd_prod.json`, `xauusd_prod.json`) tương ứng với một cấu hình cho một cặp tiền hoặc một chiến lược cụ thể.

### Cấu trúc tệp `.json`

```json
{
  "mt5_credentials": {
    "login": 12345678,
    "password": "your_password",
    "server": "Your_Server_Name"
  },
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "chat_id": "YOUR_TELEGRAM_CHAT_ID"
  },
  "trading": {
    "live_symbol": "BTCUSD",
    "magic_number": 234003,
    "risk_percent": 0.5,
    "max_open_trades": 2,
    "close_on_friday": false,
    "...": "..."
  },
  "strategy": {
    "active_strategy": "M15FilteredScalpingStrategy",
    "M15FilteredScalpingStrategy": {
      "adx_trend_threshold": 25,
      "...": "..."
    },
    "...": {}
  }
}
```

1.  **`mt5_credentials`**: Điền thông tin đăng nhập tài khoản MT5 của bạn.
2.  **`telegram`**:
    -   `enabled`: Đặt là `true` để bật thông báo.
    -   `bot_token`: Token của bot Telegram bạn tạo từ BotFather.
    -   `chat_id`: ID của cuộc trò chuyện (cá nhân hoặc nhóm) mà bạn muốn bot gửi tin nhắn đến.
3.  **`trading`**: Chứa các tham số giao dịch chung.
    -   `live_symbol`: Ký hiệu của cặp tiền/hàng hóa trên sàn MT5 (ví dụ: `XAUUSDm`, `BTCUSD`).
    -   `magic_number`: Một số nguyên duy nhất để bot nhận diện các lệnh của chính nó. **Mỗi cấu hình bot nên có một magic_number khác nhau.**
    -   `risk_percent`: Phần trăm rủi ro trên mỗi lệnh (ví dụ: `1.5` tương đương 1.5%).
    -   `max_open_trades`: Số lượng lệnh tối đa được phép mở cùng lúc.
    -   `close_on_friday`: Đặt là `true` nếu bạn muốn bot đóng tất cả các lệnh vào cuối ngày thứ Sáu.
4.  **`strategy`**:
    -   `active_strategy`: Tên của lớp chiến lược sẽ được sử dụng (phải khớp với tên lớp trong các file `*.py` ở thư mục `src`).
    -   Các mục còn lại chứa tham số chi tiết cho từng chiến lược.

## Hướng Dẫn Sử Dụng

### Chạy Bot

1.  Đảm bảo bạn đã kích hoạt môi trường ảo `(ta_env)`.
2.  Sử dụng lệnh `python` để chạy file `run_live.py` và truyền vào tên của tệp cấu hình (không bao gồm `.json`).

    **Ví dụ:**

    - Để chạy bot với cấu hình `xauusd_prod.json`:
      ```bash
      python production/run_live.py xauusd_prod
      ```

    - Để chạy bot với cấu hình `btcusd_prod.json`:
      ```bash
      python production/run_live.py btcusd_prod
      ```

    Bot sẽ bắt đầu chạy, kết nối đến MT5 và gửi thông báo khởi động qua Telegram (nếu được bật).

### Dừng Bot

Sử dụng tệp `stop_bot.bat` để dừng bot một cách an toàn.

1.  Chạy file `stop_bot.bat`.
2.  Một menu sẽ hiện ra cho phép bạn chọn bot cần dừng hoặc dừng tất cả.
3.  Sau khi chọn, script sẽ gửi tín hiệu dừng đến bot. Bot sẽ nhận tín hiệu, đóng tất cả các lệnh đang mở, hủy các lệnh chờ và gửi thông báo cuối cùng trước khi thoát hoàn toàn.

Bạn cũng có thể dừng bot bằng cách nhấn `Ctrl + C` trong cửa sổ terminal đang chạy bot.