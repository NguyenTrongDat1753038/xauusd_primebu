# 🤖 TradeBot Hub - Automated Trading System

**A professional, production-ready trading bot system for MetaTrader 5 with web dashboard, real-time bot management, and advanced risk management.**

> **Quick Start**: Run `start_all_services.bat` and open http://localhost:3000

---

## 📋 Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## ✨ Features

### 🎯 Core Trading
- **Multi-Strategy Support**: XAUUSD Scalping, EURGBP Swing, BTCUSD Trend, CPR Volume Profile
- **Advanced Risk Management**:
  - Dynamic lot sizing based on account balance
  - Circuit breaker for daily loss limits
  - Trailing stops (linear & tiered)
  - Breakeven protection
- **Real-time Order Management**:
  - Automatic position scaling
  - Dynamic SL/TP adjustment
  - Pending order auto-cancellation
  - Friday EOD auto-close

### 🖥️ Web Dashboard
- **Live Bot Control**: Start/Stop bots from browser
- **Real-time Monitoring**: Status, P&L, win rate, trade count
- **Trading Logs**: Live stream of bot trades and actions
- **Process Management**: View, monitor, and kill processes
- **Reports**: PDF generation with trading statistics
- **PWA Ready**: Install as app, offline support

### 🔧 Backend System
- **FastAPI**: High-performance REST API
- **Celery + Redis**: Async task queue for bot management
- **WebSocket**: Real-time updates to dashboard
- **MetaTrader 5 Integration**: Direct API connection
- **Telegram Notifications**: Instant trade alerts

---

## 🚀 Quick Start

### 1️⃣ Prerequisites
```powershell
# Check Python version (must be 3.10+)
python --version

# Check Node.js (for frontend)
node --version

# Optional: Install Redis (for bot management)
docker run -d -p 6379:6379 redis:latest
```

### 2️⃣ One Command Startup
```powershell
# Windows - Run this single command
start_all_services.bat

# PowerShell (more robust)
.\start_all_services.ps1
```

### 3️⃣ Open Dashboard
Open your browser: **http://localhost:3000**

### 4️⃣ Start Trading
Click "Start" on any bot card. Done! 🎉

---

## 💻 System Requirements

| Component | Requirement | Notes |
|-----------|-------------|-------|
| **OS** | Windows 10/11 | Required for MT5 integration |
| **Python** | 3.10+ | Recommended: 3.11 LTS |
| **Node.js** | 16+ | For frontend development |
| **MetaTrader 5** | Latest | Installed & logged in |
| **Redis** | 6+ | Optional but recommended (for bot management) |
| **RAM** | 4GB+ | 2GB minimum, 8GB+ recommended |
| **Disk** | 2GB+ | For bot logs and data |

---

## 📦 Installation

See [QUICK_START.md](QUICK_START.md) for detailed setup instructions.

### Quick Installation Steps

```powershell
# 1. Navigate to project
cd D:\Code\XAU_Bot_Predict

# 2. Activate virtual environment
.\ta_env\Scripts\activate.bat

# 3. Install dependencies
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. Setup MT5 Credentials
# Edit configs/xauusd_prod.json with your MT5 login details

# 5. Start everything
start_all_services.bat
```

---

## 🎮 Usage

### Via Web Dashboard (Recommended)
1. Open http://localhost:3000
2. **Dashboard Tab**: View all bots, click Start/Stop
3. **Bots Tab**: Monitor processes and logs
4. **Reports Tab**: Generate & download trading reports
5. **Remote Tab**: Server info and remote control
6. **Settings Tab**: Configure MT5 credentials

### Via Command Line
```powershell
# Start specific bot
python production/run_live.py xauusd_prod

# Check bot status
check_bot_status.bat

# Stop all bots
stop_bot.bat
```

---

## ⚙️ Configuration

### Bot Profiles
Located in `configs/`:
- `xauusd_prod.json` - Gold scalping (M1 timeframe)
- `eurgbp_prod.json` - Conservative swing (H1, low risk)
- `eurgbp_prod_high_risk.json` - Aggressive swing (H1, high risk)
- `btcusd_prod.json` - Trend following (H4)

### MT5 Credentials
Edit in `configs/<bot>.json`:
```json
{
  "mt5_credentials": {
    "login": 272716800,
    "password": "your_password",
    "server": "Exness-MT5Trial14"
  },
  ...
}
```

### Telegram Notifications
```json
{
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

---

## 🧪 Testing & Verification

```powershell
# Health check
check_bot_status.bat

# Test APIs
curl http://localhost:8000/docs          # Swagger UI
curl http://localhost:3000               # Frontend

# Test Redis
redis-cli ping

# View logs
# Check terminal windows for real-time logs
```

---

## ⚠️ Troubleshooting

### "Redis not found" Error
See [REDIS_SETUP.md](REDIS_SETUP.md) for setup options:
```powershell
docker run -d -p 6379:6379 redis:latest  # Docker (easiest)
wsl redis-server                          # WSL
setup_redis.bat                           # Interactive helper
```

### Bot won't start from dashboard
1. Check Celery Worker is running (2nd terminal)
2. Check Redis is running: `redis-cli ping`
3. View Celery logs for errors
4. Try manual: `python production/run_live.py xauusd_prod`

### Port already in use
```powershell
# Find and kill process using port
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

See [BOT_START_GUIDE.md](BOT_START_GUIDE.md) for detailed troubleshooting.

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [QUICK_START.md](QUICK_START.md) | Complete setup & configuration guide |
| [BOT_START_GUIDE.md](BOT_START_GUIDE.md) | Troubleshoot bot startup issues |
| [REDIS_SETUP.md](REDIS_SETUP.md) | Redis installation options |

---

## 📁 Project Structure

```
XAU_Bot_Predict/
├── app/                          # FastAPI backend
│   ├── main.py                   # Application entry
│   └── routers/
│       └── bots.py              # Bot control API
├── frontend/                      # Express.js + Alpine.js dashboard
│   ├── server.js                # Express server
│   ├── index.html               # Main UI
│   └── package.json
├── production/
│   └── run_live.py              # Bot trading engine
├── tasks/
│   ├── bot_tasks.py             # Celery tasks
│   └── celery_worker.py         # Celery config
├── configs/                       # Bot configuration files
├── src/                          # Bot strategies & utilities
├── ta_env/                       # Python virtual environment
├── start_all_services.bat        # 🚀 Start everything
├── start_all_services.ps1        # PowerShell version
├── setup_redis.bat               # Redis setup helper
└── check_bot_status.bat          # Check running bots
```

---

## 🎓 Key Technologies

- **Backend**: FastAPI, Celery, Redis
- **Frontend**: Express.js, Alpine.js, Tailwind CSS, DaisyUI
- **Trading**: MetaTrader 5 Python API
- **Database**: Redis (in-memory cache)
- **Documentation**: Swagger/OpenAPI

---

## 📞 Support & Troubleshooting

1. **Check Logs**: View output in terminal windows
2. **Run Health Check**: `check_bot_status.bat`
3. **View Errors**: Browser Console (F12) or terminal logs
4. **Enable Debug**: Set log level to DEBUG in config
5. **See Documentation**: Check relevant .md files above

---

## 📝 Original Documentation

For detailed technical information about bot strategies, see original README below:

---

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