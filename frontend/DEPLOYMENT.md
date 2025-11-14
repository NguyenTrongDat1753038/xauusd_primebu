# TradeBot Hub Frontend - Deployment Guide

This guide covers deploying TradeBot Hub to various environments.

## Table of Contents

1. [Local Development](#local-development)
2. [Linux/macOS Deployment](#linuxmacos-deployment)
3. [Windows Deployment](#windows-deployment)
4. [Docker Deployment](#docker-deployment)
5. [Cloud Deployment](#cloud-deployment)
6. [Monitoring & Maintenance](#monitoring--maintenance)

---

## Local Development

### Quick Start (5 minutes)

```bash
# 1. Navigate to frontend
cd frontend

# 2. Run setup script
bash setup.sh          # Linux/macOS
setup.bat             # Windows

# 3. Start development server
npm start

# 4. Open browser
# http://localhost:3000
```

### Development Mode Features

- Hot reload with nodemon (optional)
- Detailed console logging
- Source maps for debugging
- Mock data for testing
- CORS enabled for all origins

### Enable Auto-reload

```bash
# Install nodemon globally
npm install -g nodemon

# Start with auto-reload
npx nodemon server.js

# Or use npm script (add to package.json)
npm run dev
```

---

## Linux/macOS Deployment

### 1. System Requirements

```bash
# Check Node.js
node --version  # v16+
npm --version   # v8+

# Check system resources
df -h           # Disk space (100MB minimum)
free -h         # RAM (512MB minimum)
nproc           # CPU cores
```

### 2. Installation

```bash
# Clone or navigate to project
cd frontend

# Install dependencies
npm ci --only=production

# Create required directories
mkdir -p logs public/icons public/screenshots reports

# Copy and configure environment
cp .env.example .env
nano .env  # Edit configuration
```

### 3. Option A: Systemd Service (Recommended)

**Create service file:**

```bash
sudo nano /etc/systemd/system/tradebot-hub.service
```

**Paste this content:**

```ini
[Unit]
Description=TradeBot Hub Frontend Service
After=network.target
Documentation=https://github.com/yourusername/tradebot-hub

[Service]
Type=simple
User=trader
Group=trader
WorkingDirectory=/home/trader/XAU_Bot_Predict/frontend
Environment="NODE_ENV=production"
Environment="PORT=3000"
Environment="FASTAPI_URL=http://localhost:8000"
ExecStart=/usr/bin/node /home/trader/XAU_Bot_Predict/frontend/server.js
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tradebot-hub

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable tradebot-hub.service
sudo systemctl start tradebot-hub.service
sudo systemctl status tradebot-hub.service

# View logs
sudo journalctl -u tradebot-hub.service -f
```

### 3. Option B: PM2 (Process Manager)

**Install PM2 globally:**

```bash
npm install -g pm2
```

**Create ecosystem config:**

```bash
cat > ecosystem.config.js << 'EOF'
module.exports = {
  apps: [{
    name: 'tradebot-hub',
    script: './server.js',
    instances: 1,
    exec_mode: 'cluster',
    watch: false,
    max_memory_restart: '512M',
    env: {
      NODE_ENV: 'production',
      PORT: 3000,
      FASTAPI_URL: 'http://localhost:8000'
    },
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z'
  }]
};
EOF
```

**Start with PM2:**

```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup

# View logs
pm2 logs tradebot-hub

# Monitor
pm2 monit
```

### 4. Option C: Nginx Reverse Proxy

**Install Nginx:**

```bash
sudo apt-get install nginx
```

**Configure Nginx:**

```bash
sudo nano /etc/nginx/sites-available/tradebot-hub
```

**Add this configuration:**

```nginx
upstream nodejs {
    server 127.0.0.1:3000;
}

server {
    listen 80;
    server_name your-domain.com;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Compression
    gzip on;
    gzip_types text/plain text/css text/javascript application/json application/javascript;
    gzip_min_length 1000;
    gzip_proxied any;

    # Logging
    access_log /var/log/nginx/tradebot-hub-access.log;
    error_log /var/log/nginx/tradebot-hub-error.log;

    # Location
    location / {
        proxy_pass http://nodejs;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # Static files cache
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
```

**Enable site and test:**

```bash
sudo ln -s /etc/nginx/sites-available/tradebot-hub /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 5. SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt-get install certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Renew automatically
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

---

## Windows Deployment

### 1. Prerequisites

- Node.js 16+ installed
- Windows 10/11
- Administrator access (optional, for service installation)

### 2. Installation

```bash
# Navigate to frontend
cd frontend

# Run setup batch file
setup.bat

# Start server
npm start
```

### 3. Option A: Manual Startup

Create `start_frontend.bat`:

```batch
@echo off
cd /d "%~dp0"
set NODE_ENV=production
node server.js
pause
```

Run it to start the server.

### 3. Option B: Task Scheduler

**Create scheduled task:**

1. Open Task Scheduler
2. Create Basic Task → "TradeBot Hub Frontend"
3. Trigger: "At system startup"
4. Action: Start program
   - Program: `C:\nodejs\node.exe`
   - Arguments: `C:\path\to\frontend\server.js`
   - Start in: `C:\path\to\frontend\`
5. Conditions:
   - [x] Wake the computer to run this task
   - [x] Run with highest privileges
6. Finish

### 3. Option C: NSSM (Non-Sucking Service Manager)

```bash
# Download NSSM
# https://nssm.cc/download

# Install as service
nssm install TradeBot-Hub-Frontend "C:\nodejs\node.exe" "C:\path\to\frontend\server.js"
nssm set TradeBot-Hub-Frontend AppDirectory "C:\path\to\frontend"
nssm set TradeBot-Hub-Frontend AppStdout "C:\path\to\frontend\logs\stdout.log"
nssm set TradeBot-Hub-Frontend AppStderr "C:\path\to\frontend\logs\stderr.log"

# Start service
nssm start TradeBot-Hub-Frontend

# View status
nssm status TradeBot-Hub-Frontend
```

---

## Docker Deployment

### 1. Build Image

```bash
docker build -t tradebot-hub-frontend:latest .
```

### 2. Run Container

```bash
docker run -d \
  --name tradebot-hub \
  -p 3000:3000 \
  -e NODE_ENV=production \
  -e PORT=3000 \
  -e FASTAPI_URL=http://localhost:8000 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/reports:/app/reports \
  tradebot-hub-frontend:latest
```

### 3. Docker Compose (Recommended)

From project root, create/update `docker-compose.yml`:

```yaml
version: '3.8'

services:
  # FastAPI Backend
  fastapi:
    image: python:3.11-slim
    working_dir: /app
    command: python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - PYTHONUNBUFFERED=1
    volumes:
      - .:/app
    depends_on:
      - redis
      - postgres
    networks:
      - tradebot-network

  # Frontend
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - PORT=3000
      - FASTAPI_URL=http://fastapi:8000
    volumes:
      - ./frontend/logs:/app/logs
      - ./frontend/reports:/app/reports
    depends_on:
      - fastapi
    networks:
      - tradebot-network
    restart: unless-stopped

  # Redis (for Celery)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    networks:
      - tradebot-network
    restart: unless-stopped

  # PostgreSQL (for database)
  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=tradebot
      - POSTGRES_USER=trader
      - POSTGRES_PASSWORD=secure_password
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - tradebot-network
    restart: unless-stopped

  # Celery Worker (optional)
  celery:
    build:
      context: .
      dockerfile: Dockerfile
    command: celery -A tasks.celery_worker worker --loglevel=info
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    depends_on:
      - redis
    networks:
      - tradebot-network
    restart: unless-stopped

volumes:
  redis-data:
  postgres-data:

networks:
  tradebot-network:
    driver: bridge
```

**Start all services:**

```bash
docker-compose up -d

# View logs
docker-compose logs -f frontend

# Stop all services
docker-compose down
```

### 4. Push to Registry

```bash
# Tag image
docker tag tradebot-hub-frontend:latest myregistry/tradebot-hub-frontend:1.0.0

# Push to registry
docker push myregistry/tradebot-hub-frontend:1.0.0

# Pull from registry
docker pull myregistry/tradebot-hub-frontend:1.0.0
```

---

## Cloud Deployment

### Heroku

```bash
# Login
heroku login

# Create app
heroku create tradebot-hub

# Set environment variables
heroku config:set NODE_ENV=production
heroku config:set FASTAPI_URL=https://your-fastapi-app.herokuapp.com

# Deploy
git push heroku main

# View logs
heroku logs -t
```

### AWS EC2

```bash
# Connect to instance
ssh -i your-key.pem ec2-user@your-instance-ip

# Install Node.js
curl https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo yum install nodejs -y

# Clone and setup
git clone https://github.com/yourusername/tradebot-hub.git
cd tradebot-hub/frontend
npm install --production

# Start with PM2
npm install -g pm2
pm2 start server.js --name tradebot-hub
pm2 save
pm2 startup
```

### Google Cloud Run

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/tradebot-hub-frontend

# Deploy
gcloud run deploy tradebot-hub-frontend \
  --image gcr.io/PROJECT_ID/tradebot-hub-frontend \
  --platform managed \
  --region us-central1 \
  --set-env-vars NODE_ENV=production,FASTAPI_URL=https://your-backend.com
```

### DigitalOcean App Platform

1. Push code to GitHub
2. Create new App
3. Select repository
4. Configure:
   - Build command: `npm install --production`
   - Run command: `npm start`
   - Environment: NODE_ENV=production
5. Deploy

---

## Monitoring & Maintenance

### Health Checks

```bash
# API health check
curl http://localhost:3000/api/system/status

# WebSocket check
wscat -c ws://localhost:3000
```

### Log Rotation

**Using logrotate (Linux):**

```bash
sudo nano /etc/logrotate.d/tradebot-hub
```

```
/home/trader/XAU_Bot_Predict/frontend/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 trader trader
    sharedscripts
    postrotate
        systemctl reload tradebot-hub.service > /dev/null 2>&1 || true
    endscript
}
```

### Backup Strategy

**Daily backup script:**

```bash
#!/bin/bash
BACKUP_DIR="/backups/tradebot-hub"
SOURCE_DIR="/home/trader/XAU_Bot_Predict/frontend"

mkdir -p $BACKUP_DIR
DATE=$(date +%Y%m%d_%H%M%S)

# Backup logs and reports
tar -czf $BACKUP_DIR/backup_$DATE.tar.gz \
    $SOURCE_DIR/logs \
    $SOURCE_DIR/reports

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/backup_$DATE.tar.gz"
```

### Monitoring with PM2+

```bash
# Install PM2 Plus
pm2 install pm2-auto-pull  # Auto pull from GitHub
pm2 install pm2-logrotate  # Automatic log rotation

# Link to PM2+ dashboard
pm2 link
```

---

## Troubleshooting Deployment

| Issue | Solution |
|-------|----------|
| Port already in use | Kill process: `lsof -i :3000 \| awk '{print $2}' \| xargs kill` |
| Cannot connect to backend | Verify FastAPI is running: `curl http://localhost:8000/docs` |
| High memory usage | Check logs for memory leaks; restart service: `pm2 restart all` |
| SSL certificate issue | Renew certificate: `sudo certbot renew` |
| Docker image too large | Use Alpine base image; optimize Dockerfile |
| Slow PDF generation | Reduce timeout; enable cache; use lighter CSS |

---

## Performance Tuning

### Node.js Optimization

```bash
# Increase max connections
ulimit -n 65535

# Enable clustering (multiple workers)
NODE_CLUSTER_WORKERS=4 npm start
```

### Nginx Optimization

```nginx
# In nginx config
worker_processes auto;
worker_connections 1024;
keepalive_timeout 65;
```

---

## Security Hardening

**Pre-deployment checklist:**

- [ ] Enable HTTPS/TLS
- [ ] Set strong NODE_ENV
- [ ] Configure CORS properly
- [ ] Enable rate limiting
- [ ] Add authentication layer
- [ ] Sanitize user input
- [ ] Update all dependencies: `npm audit fix`
- [ ] Remove dev dependencies: `npm install --production`
- [ ] Enable security headers
- [ ] Set up log monitoring
- [ ] Configure firewall rules
- [ ] Regular security updates

---

**For more help, see:**
- README.md - Full documentation
- QUICKSTART.md - Quick start guide
- .env.example - Configuration reference

**Last Updated:** January 2024
