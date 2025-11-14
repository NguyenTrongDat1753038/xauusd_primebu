# TradeBot Hub - Frontend PWA Dashboard

Professional web application for managing and monitoring automated trading bots. Built with Tailwind CSS, Alpine.js, Express.js, and WebSocket for real-time updates.

## Features

✨ **Core Functionality**
- 📊 Dashboard with real-time bot status and performance metrics
- 🤖 Process management (start/stop bots, view logs)
- 📈 PDF report generation with trade statistics
- 🌐 Remote access via local IP and QR code
- ⚙️ Settings management for MT5, notifications, and auto-start

🎨 **User Interface**
- Dark mode UI with Tailwind CSS + DaisyUI components
- Responsive design (desktop-first, mobile-friendly)
- Real-time charts with Chart.js and ApexCharts
- Floating action buttons for quick bot control
- Collapsible sidebar for navigation

🔌 **Integration**
- WebSocket for real-time bot status updates
- Proxy to FastAPI backend (`http://localhost:8000`)
- Process monitoring and log streaming
- SSE (Server-Sent Events) for log streaming

📱 **PWA Features**
- Service Worker for offline support
- Installable on desktop and mobile
- Background sync for offline actions
- Push notifications
- Works with or without internet

## Project Structure

```
frontend/
├── index.html          # Main HTML scaffold with Tailwind + DaisyUI
├── app.js              # Alpine.js app logic (routing, API, WebSocket)
├── server.js           # Express.js backend (static server, API, WebSocket)
├── sw.js               # Service Worker (offline support, caching)
├── manifest.json       # PWA manifest (installability, icons)
├── package.json        # Node.js dependencies
├── Dockerfile          # Docker image for deployment
├── README.md           # This file
│
├── public/             # Static files (created after npm install)
│   ├── icons/          # App icons (various sizes)
│   └── screenshots/    # App screenshots for PWA
│
└── logs/               # Application logs directory
```

## Installation

### Prerequisites

- **Node.js 16+** ([Download](https://nodejs.org/))
- **Python 3.8+** with FastAPI backend running on `http://localhost:8000`
- **Chrome/Edge 90+** or modern browser for PWA support

### Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

   This installs:
   - `express` - Web server and static file serving
   - `ws` - WebSocket for real-time updates
   - `puppeteer` - PDF generation
   - `express-static-gzip` - Gzip compression for static files

3. **Create public directory structure:**
   ```bash
   mkdir -p public/icons public/screenshots
   ```

4. **(Optional) Add app icons** in `public/icons/`:
   - `icon-72x72.png`
   - `icon-96x96.png`
   - `icon-128x128.png`
   - `icon-192x192.png`
   - `icon-512x512.png`
   - `maskable-icon-192x192.png` (for mobile home screen)

## Running the Application

### Development Mode

```bash
npm start
```

The server will start on `http://localhost:3000`.

Open in browser:
```
http://localhost:3000
```

Or access via local IP (for remote access):
```
http://192.168.x.x:3000  # Replace with your actual IP
```

### Debug Mode with Logs

```bash
DEBUG=tradebot-hub:* npm start
```

### Run with Node Development Tools

```bash
npx nodemon server.js
```

(Requires `npm install --save-dev nodemon`)

## API Endpoints

### System Information
- `GET /api/system/status` - System uptime, memory, CPU info
- `GET /api/network/ip` - Local IP and server URL

### Bot Control
- `GET /api/bots` - Get list of bots and status (proxied to FastAPI)
- `POST /api/bots/start` - Start a bot
- `POST /api/bots/stop` - Stop a bot

### Process Management
- `GET /api/processes` - List running Python processes
- `POST /api/processes/:pid/kill` - Terminate a process

### Reports
- `POST /api/reports/generate` - Generate PDF report with Puppeteer
- `GET /api/logs/stream` - Stream logs via Server-Sent Events

### WebSocket Events
- `connection` - Client connected
- `bot_status` - Bot running status changed
- `log` - New log message
- `metrics_update` - System metrics update
- `process_update` - Process information changed

## Configuration

### Environment Variables

```bash
# Server port (default: 3000)
PORT=3000

# FastAPI backend URL (default: http://localhost:8000)
FASTAPI_URL=http://localhost:8000

# Node environment
NODE_ENV=production
```

### Configuration File (Optional)

Create `config.json` in the frontend directory:

```json
{
  "port": 3000,
  "fastapi_url": "http://localhost:8000",
  "redis_url": "redis://localhost:6379/0",
  "log_level": "info",
  "enable_compression": true,
  "session_timeout": 3600000
}
```

## Deployment

### Local Development (Current Mini PC)

1. **Start FastAPI backend** (separate terminal):
   ```bash
   cd ..
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Start Celery worker** (if using bot management):
   ```bash
   celery -A tasks.celery_worker worker --loglevel=info
   ```

3. **Start Redis** (if using docker-compose):
   ```bash
   docker-compose up -d
   ```

4. **Start frontend**:
   ```bash
   cd frontend
   npm start
   ```

### Systemd Service (24/7 Daemon on Linux)

Create `/etc/systemd/system/tradebot-hub.service`:

```ini
[Unit]
Description=TradeBot Hub Frontend Service
After=network.target

[Service]
Type=simple
User=trader
WorkingDirectory=/home/trader/XAU_Bot_Predict/frontend
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable tradebot-hub.service
sudo systemctl start tradebot-hub.service
sudo systemctl status tradebot-hub.service
```

### PM2 (Process Manager for Node.js)

Install PM2:
```bash
npm install -g pm2
```

Create `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [{
    name: 'tradebot-hub',
    script: './server.js',
    instances: 1,
    exec_mode: 'cluster',
    env: {
      NODE_ENV: 'production',
      PORT: 3000
    },
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log'
  }]
};
```

Start with PM2:
```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

### Docker Deployment

Build Docker image:
```bash
docker build -t tradebot-hub-frontend:latest .
```

Run container:
```bash
docker run -d \
  --name tradebot-hub \
  -p 3000:3000 \
  -e FASTAPI_URL=http://fastapi:8000 \
  -v $(pwd)/logs:/app/logs \
  tradebot-hub-frontend:latest
```

Or use Docker Compose (from root directory):
```bash
docker-compose up -d
```

### Remote Access

1. **Via ngrok** (for temporary public URL):
   ```bash
   ngrok http 3000
   ```

2. **Via Tailscale** (for private network):
   ```bash
   tailscale up
   ```
   Then access: `http://<device-name>:3000`

3. **Via SSH tunnel** (from remote machine):
   ```bash
   ssh -L 3000:localhost:3000 user@mini-pc-ip
   ```

4. **Direct local IP** (within home network):
   ```
   http://192.168.x.x:3000
   ```

## PWA Installation

### On Desktop (Chrome/Edge)

1. Open `http://localhost:3000` in Chrome/Edge
2. Click the **Install** button in the address bar
3. Click **Install**
4. App will appear in Start Menu and taskbar

### On Mobile

1. Open URL in mobile Chrome
2. Tap the menu (three dots)
3. Tap **"Install app"** or **"Add to home screen"**
4. App will be installed like native app

### Features When Installed

- ✅ Works offline (with cached assets)
- ✅ Standalone window (no browser chrome)
- ✅ Push notifications
- ✅ Background sync for logs/reports
- ✅ Add to home screen

## Troubleshooting

### Port Already in Use

```bash
# Find process on port 3000
lsof -i :3000  # macOS/Linux
netstat -ano | findstr :3000  # Windows

# Kill the process
kill -9 <PID>  # macOS/Linux
taskkill /PID <PID> /F  # Windows
```

### WebSocket Connection Failed

- Ensure FastAPI backend is running on `http://localhost:8000`
- Check firewall allows port 3000
- Verify `FASTAPI_URL` environment variable is correct

### PDF Generation Fails

```bash
# Install Chromium (required by Puppeteer)
npx puppeteer browsers install chrome
```

### Service Worker Not Updating

```javascript
// In browser console
navigator.serviceWorker.getRegistrations().then(registrations => {
  registrations.forEach(reg => reg.unregister());
});
location.reload();
```

### High Memory Usage

- Limit Puppeteer processes: `PUPPETEER_ARGS=--disable-gpu`
- Reduce log retention (clear old logs periodically)
- Restart server: `pm2 restart tradebot-hub`

## Performance Optimization

### Enable Compression

```bash
# Already enabled in server.js with express-static-gzip
# Compresses CSS, JS, JSON responses with Brotli/Gzip
```

### Reduce Bundle Size

```bash
# Check bundle size
npx webpack-bundle-analyzer dist/stats.json

# Tree-shake unused code in Alpine.js
# Remove unused DaisyUI components
```

### Caching Strategy

- Static assets: 1 hour cache
- API responses: Cached with Network-first strategy
- Offline fallback: Last successful response

## Security Considerations

### Production Checklist

- [ ] Set `NODE_ENV=production`
- [ ] Use HTTPS with valid certificate
- [ ] Enable CORS only for trusted origins
- [ ] Add authentication (JWT/OAuth2)
- [ ] Rate limiting for API endpoints
- [ ] Sanitize user input (especially in logs/reports)
- [ ] Regular security updates: `npm audit fix`
- [ ] Hide error details in production

### Example HTTPS Setup

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes

# Or use Let's Encrypt (Certbot)
sudo certbot certonly --standalone -d your-domain.com
```

## Development

### Code Structure

- **index.html** - Static HTML scaffold (Tailwind + DaisyUI)
- **app.js** - Alpine.js app state and logic
- **server.js** - Express.js backend with WebSocket
- **sw.js** - Service Worker for offline support

### Adding New Features

1. **Add UI in index.html** (new page section)
2. **Add logic in app.js** (Alpine methods)
3. **Add API endpoint in server.js** (if needed)
4. **Update navigation** in `navItems` array

### Testing

```bash
# Unit tests (Jest)
npm test

# E2E tests (Playwright)
npm run test:e2e

# Load testing
npm run test:load
```

### Git Workflow

```bash
git checkout -b feature/new-feature
# Make changes
git add .
git commit -m "feat: Add new feature"
git push origin feature/new-feature
# Create Pull Request
```

## Monitoring

### Logs

```bash
# Real-time logs
npm start 2>&1 | tee logs/app.log

# PM2 logs
pm2 logs tradebot-hub

# Docker logs
docker logs -f tradebot-hub
```

### Metrics

- Memory usage: Task Manager or `docker stats`
- CPU usage: Check system performance
- Request count: Check `server.js` console output
- WebSocket connections: `wss.clients.size` in server.js

### Health Check

```bash
curl http://localhost:3000/api/system/status
```

Should return:
```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "uptime": 3600,
  "hostname": "mini-pc",
  "memory": {
    "total": 8589934592,
    "free": 2147483648
  }
}
```

## Dependencies

### Production

- **express** (4.18+) - Web framework
- **ws** (8.13+) - WebSocket library
- **puppeteer** (20.0+) - PDF generation
- **express-static-gzip** (3.4+) - Static file compression

### Development (Optional)

- **nodemon** - Auto-restart on file changes
- **webpack-bundle-analyzer** - Analyze bundle size
- **jest** - Unit testing
- **playwright** - E2E testing

## License

Proprietary - TradeBot Hub
All rights reserved.

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review server.js console logs
3. Check browser DevTools console
4. Verify FastAPI backend is running: `curl http://localhost:8000/docs`

## Changelog

### v1.0.0 (Initial Release)
- ✅ Dashboard with bot cards
- ✅ Process management
- ✅ PDF report generation
- ✅ Real-time WebSocket updates
- ✅ PWA support
- ✅ Dark mode UI
- ✅ Remote access via QR code

## Future Enhancements

- [ ] User authentication (login/multi-user)
- [ ] Historical trade analysis and backtesting viewer
- [ ] Advanced charting with technical indicators
- [ ] Mobile app (React Native)
- [ ] Cloud backup for reports and settings
- [ ] Email/SMS alerts
- [ ] Webhook integration for 3rd party services
- [ ] API key management for external APIs
- [ ] Database persistence (TimescaleDB integration)

---

**Built with ❤️ for traders and developers**
