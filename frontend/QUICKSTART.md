# TradeBot Hub - Quick Start Guide

## 5-Minute Setup

### Step 1: Verify Prerequisites

```bash
# Check Node.js is installed
node --version  # Should be v16+
npm --version   # Should be v8+

# Check Python FastAPI backend is running
curl http://localhost:8000/docs
# Should show FastAPI docs page
```

### Step 2: Install Frontend

```bash
cd frontend

# Install Node.js dependencies
npm install

# Verify installation
npm list --depth=0
```

### Step 3: Start the Server

```bash
npm start
```

You should see:
```
╔════════════════════════════════════════════════════════════╗
║         TradeBot Hub - Backend Server v1.0.0              ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  🚀 Server running at http://localhost:3000/              ║
║  📡 WebSocket: ws://localhost:3000                        ║
║  🔌 FastAPI Backend: http://localhost:8000                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
```

### Step 4: Access the Dashboard

Open your browser:
```
http://localhost:3000
```

Or access via local IP (for remote access):
```bash
# Find your local IP
hostname -I  # Linux/macOS
ipconfig     # Windows

# Then visit
http://192.168.x.x:3000
```

## Running All Services Together

### Terminal 1: Python FastAPI Backend

```bash
cd ..  # Go to project root
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2: Celery Worker (for bot management)

```bash
celery -A tasks.celery_worker worker --loglevel=info
```

### Terminal 3: Node.js Frontend

```bash
cd frontend
npm start
```

### Terminal 4 (Optional): Redis (if using docker-compose)

```bash
docker-compose up
```

## File Structure

```
frontend/
├── index.html          # Main UI (Tailwind + DaisyUI + Alpine.js)
├── app.js              # App logic (routing, API, WebSocket)
├── server.js           # Express backend (static server, WebSocket, PDF)
├── sw.js               # Service Worker (offline support)
├── manifest.json       # PWA manifest
├── package.json        # Node.js dependencies
├── Dockerfile          # Docker image
├── .env.example        # Configuration template
├── README.md           # Full documentation
└── logs/               # Application logs
```

## Common Tasks

### View Real-time Logs

```bash
# With PM2
pm2 logs tradebot-hub

# Or with Docker
docker logs -f tradebot-hub

# Or direct npm
npm start 2>&1 | tee logs/app.log
```

### Check System Status

```bash
curl http://localhost:3000/api/system/status | jq .
```

### Get Bot Status

```bash
curl http://localhost:3000/api/bots | jq .
```

### Start a Bot

```bash
curl -X POST http://localhost:3000/api/bots/start \
  -H "Content-Type: application/json" \
  -d '{"bot_id": "xauusd"}'
```

### Generate PDF Report

```bash
curl -X POST http://localhost:3000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{
    "bots": ["xauusd", "eurgbp"],
    "type": "detailed",
    "dateRange": "2024-01-01 to 2024-01-15"
  }' > report.pdf
```

## Troubleshooting

### Port 3000 Already in Use

```bash
# Find what's using port 3000
lsof -i :3000

# Kill it
kill -9 <PID>

# Or use different port
PORT=3001 npm start
```

### Cannot Connect to FastAPI Backend

```bash
# Check if backend is running
curl -v http://localhost:8000/docs

# If not, start it (in separate terminal)
cd ..
python -m uvicorn app.main:app --reload
```

### WebSocket Connection Error

- Check browser DevTools (F12) → Console for errors
- Verify frontend server is running: `npm start`
- Check firewall allows port 3000
- Try accessing via `localhost` instead of IP

### PDF Generation Fails

```bash
# Install Chromium manually
npx puppeteer browsers install chrome
```

## Next Steps

1. **Install as PWA**
   - Open browser DevTools (F12)
   - Look for "Install" button in address bar
   - Click to install as desktop app

2. **Customize Settings**
   - Go to Settings page in dashboard
   - Configure MT5 path and notifications
   - Save settings

3. **Start Bots**
   - Dashboard page shows all available bots
   - Click toggle to start/stop
   - Watch real-time updates

4. **Generate Reports**
   - Reports page → Select date range and bots
   - Click "Generate PDF"
   - Download report with trade statistics

5. **Enable Remote Access**
   - Remote page shows local IP and QR code
   - Share IP with team members
   - Or use ngrok/Tailscale for internet access

## Performance Tips

- Use Chrome/Edge for best performance
- Keep browser cache enabled (Settings → Storage)
- Close other tabs to reduce memory usage
- Restart server weekly for memory cleanup

## Production Deployment

### Docker Deployment

```bash
docker build -t tradebot-hub:latest .
docker run -d -p 3000:3000 tradebot-hub:latest
```

### PM2 Deployment (Linux/macOS)

```bash
npm install -g pm2
pm2 start server.js --name tradebot-hub
pm2 save
pm2 startup
```

### Systemd Service (Linux)

See README.md for full systemd setup instructions.

## Features Checklist

- [x] Dashboard with bot status
- [x] Start/stop bot controls
- [x] Real-time WebSocket updates
- [x] Process monitoring
- [x] PDF report generation
- [x] Dark mode UI
- [x] PWA installable
- [x] Offline support
- [x] Remote access (IP + QR)
- [x] Settings management
- [ ] User authentication (TODO)
- [ ] Database persistence (TODO)

## Support

- Full documentation: See README.md
- API docs: `http://localhost:3000/api/system/status`
- FastAPI docs: `http://localhost:8000/docs`
- Logs: Check `frontend/logs/` directory

---

**Ready to trade! Happy botting! 🚀**
