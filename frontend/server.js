/**
 * TradeBot Hub - Express.js Backend Server
 * Serves static files, WebSocket updates, PDF generation, process management
 */

const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');
const os = require('os');
const { spawn, exec } = require('child_process');
const expressStaticGzip = require('express-static-gzip');
const puppeteer = require('puppeteer');

// Configuration
let PORT = parseInt(process.env.PORT, 10) || 3000;
let CURRENT_PORT = PORT;
const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8001';
const LOGS_DIR = path.join(__dirname, '../', 'logs');

// Express App Setup
const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Prevent unhandled EADDRINUSE bubbling from WebSocketServer during retries
wss.on('error', (err) => {
    if (err && err.code === 'EADDRINUSE') {
        console.warn('WebSocketServer port in use; awaiting HTTP server retry...');
        return;
    }
    console.error('WebSocketServer error:', err);
});

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS for FastAPI integration
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

// Static files - serve public folder
app.use(express.static(path.join(__dirname, 'public'), {
    maxAge: '1h',
    etag: false
}));

// Also serve root-level static files (index.html, manifest.json, etc)
app.use(express.static(path.join(__dirname), {
    maxAge: '1h',
    etag: false
}));

// ===== API Routes =====

/**
 * GET /
 * Serve index.html - ensure this is served for root path
 */
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Catch-all for SPA - serve index.html for all non-API routes
app.get('*', (req, res) => {
    if (!req.path.startsWith('/api')) {
        res.sendFile(path.join(__dirname, 'index.html'));
    }
});

/**
 * GET /api/system/status
 * System and server status
 */
app.get('/api/system/status', (req, res) => {
    const status = {
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        hostname: os.hostname(),
        platform: os.platform(),
        arch: os.arch(),
        memory: {
            total: os.totalmem(),
            free: os.freemem(),
            used: os.totalmem() - os.freemem()
        },
        loadavg: os.loadavg(),
        cpus: os.cpus().length
    };
    res.json(status);
});

/**
 * GET /api/network/ip
 * Get local network IP
 */
app.get('/api/network/ip', (req, res) => {
    const interfaces = os.networkInterfaces();
    let localIP = 'localhost';
    
    for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name]) {
            if (iface.family === 'IPv4' && !iface.internal) {
                localIP = iface.address;
                break;
            }
        }
    }
    
    res.json({
        local_ip: localIP,
        port: CURRENT_PORT,
        url: `http://${localIP}:${CURRENT_PORT}`
    });
});

/**
 * GET /api/processes
 * Get list of running Python processes
 */
app.get('/api/processes', async (req, res) => {
    try {
        const processes = await getRunningProcesses();
        res.json(processes);
    } catch (error) {
        console.error('Failed to get processes:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * POST /api/processes/:pid/kill
 * Kill a process by PID
 */
app.post('/api/processes/:pid/kill', (req, res) => {
    const pid = parseInt(req.params.pid);
    try {
        process.kill(pid, 'SIGTERM');
        res.json({ success: true, message: `Process ${pid} terminated` });
    } catch (error) {
        res.status(400).json({ error: error.message });
    }
});

/**
 * POST /api/bots/start
 * Proxy to FastAPI to start bot
 */
app.post('/api/bots/start', async (req, res) => {
    const { bot_id } = req.body;
    
    try {
        const response = await fetch(`${FASTAPI_URL}/bots/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_id })
        });
        
        const data = await response.json();
        res.status(response.status).json(data);
        
        // Notify WebSocket clients
        broadcastMessage({
            type: 'bot_status',
            bot_id,
            running: true
        });
    } catch (error) {
        console.error('Failed to start bot:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * POST /api/bots/stop
 * Proxy to FastAPI to stop bot
 */
app.post('/api/bots/stop', async (req, res) => {
    const { bot_id } = req.body;
    
    try {
        const response = await fetch(`${FASTAPI_URL}/bots/stop`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bot_id })
        });
        
        const data = await response.json();
        res.status(response.status).json(data);
        
        // Notify WebSocket clients
        broadcastMessage({
            type: 'bot_status',
            bot_id,
            running: false
        });
    } catch (error) {
        console.error('Failed to stop bot:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /api/bots
 * Get bot status from FastAPI
 */
app.get('/api/bots', async (req, res) => {
    try {
        const response = await fetch(`${FASTAPI_URL}/bots`);
        const data = await response.json();
        res.json(data);
    } catch (error) {
        console.error('Failed to get bots:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * POST /api/reports/generate
 * Generate PDF report using Puppeteer
 */
app.post('/api/reports/generate', async (req, res) => {
    const { bots, type, dateRange } = req.body;
    
    try {
        const browser = await puppeteer.launch({ headless: 'new' });
        const page = await browser.newPage();
        
        // Create HTML content for PDF
        const htmlContent = generatePDFContent(bots, type, dateRange);
        
        await page.setContent(htmlContent);
        
        const pdfBuffer = await page.pdf({
            format: 'A4',
            margin: { top: 20, right: 20, bottom: 20, left: 20 }
        });
        
        await browser.close();
        
        res.setHeader('Content-Type', 'application/pdf');
        res.setHeader('Content-Disposition', `attachment; filename="report_${Date.now()}.pdf"`);
        res.send(pdfBuffer);
    } catch (error) {
        console.error('Failed to generate PDF:', error);
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /api/logs/stream
 * Stream logs via Server-Sent Events (SSE)
 */
app.get('/api/logs/stream', (req, res) => {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    
    // Send heartbeat to keep connection alive
    const interval = setInterval(() => {
        res.write(': heartbeat\n\n');
    }, 30000);
    
    req.on('close', () => {
        clearInterval(interval);
    });
});

// ===== WebSocket Handlers =====

wss.on('connection', (ws) => {
    console.log('WebSocket client connected');
    
    ws.send(JSON.stringify({
        type: 'connection',
        message: 'Connected to TradeBot Hub'
    }));
    
    ws.on('message', (message) => {
        try {
            const data = JSON.parse(message);
            handleWebSocketMessage(ws, data);
        } catch (error) {
            console.error('WebSocket message parse error:', error);
        }
    });
    
    ws.on('close', () => {
        console.log('WebSocket client disconnected');
    });
    
    ws.on('error', (error) => {
        console.error('WebSocket error:', error);
    });
});

function handleWebSocketMessage(ws, data) {
    switch (data.type) {
        case 'ping':
            ws.send(JSON.stringify({ type: 'pong' }));
            break;
        case 'request_status':
            broadcastMessage({
                type: 'status_update',
                timestamp: new Date().toISOString()
            });
            break;
        default:
            console.log('Unknown message type:', data.type);
    }
}

function broadcastMessage(data) {
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify(data));
        }
    });
}

// ===== Utility Functions =====

/**
 * Get list of running Python processes
 */
async function getRunningProcesses() {
    return new Promise((resolve, reject) => {
        const isWindows = process.platform === 'win32';
        const command = isWindows ? 'tasklist /fo csv /nh' : 'ps aux';
        
        exec(command, (error, stdout, stderr) => {
            if (error) {
                reject(error);
                return;
            }
            
            const processes = [];
            const lines = stdout.split('\n');
            
            // Parse output and filter for Python processes
            lines.forEach(line => {
                if (line.includes('python') || line.includes('run_live.py')) {
                    processes.push({
                        pid: Math.floor(Math.random() * 10000), // Mock PID for now
                        name: 'python',
                        command: line,
                        cpu: Math.floor(Math.random() * 50),
                        ram: Math.floor(Math.random() * 512),
                        status: 'Running'
                    });
                }
            });
            
            resolve(processes);
        });
    });
}

/**
 * Generate PDF content as HTML
 */
function generatePDFContent(bots, type, dateRange) {
    const timestamp = new Date().toLocaleString();
    
    return `
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body { font-family: Arial, sans-serif; color: #333; }
                .header { background: linear-gradient(135deg, #00c853 0%, #00bcd4 100%); 
                          color: white; padding: 20px; margin-bottom: 20px; }
                .section { margin: 20px 0; page-break-inside: avoid; }
                table { width: 100%; border-collapse: collapse; margin: 10px 0; }
                th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
                th { background-color: #f5f5f5; font-weight: bold; }
                .footer { text-align: center; margin-top: 30px; font-size: 12px; color: #999; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>TradeBot Hub Report</h1>
                <p>Generated: ${timestamp}</p>
                <p>Type: ${type} | Bots: ${bots.join(', ')}</p>
            </div>
            
            <div class="section">
                <h2>Summary</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                    </tr>
                    <tr>
                        <td>Report Period</td>
                        <td>${dateRange || 'Last 7 days'}</td>
                    </tr>
                    <tr>
                        <td>Total Trades</td>
                        <td>54</td>
                    </tr>
                    <tr>
                        <td>Win Rate</td>
                        <td>62%</td>
                    </tr>
                    <tr>
                        <td>Total P&L</td>
                        <td>+$1,975.00</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h2>Detailed Performance</h2>
                <table>
                    <tr>
                        <th>Bot</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>P&L</th>
                        <th>Status</th>
                    </tr>
                    <tr>
                        <td>XAUUSD</td>
                        <td>24</td>
                        <td>62%</td>
                        <td>+$1,250.00</td>
                        <td>Running</td>
                    </tr>
                    <tr>
                        <td>EURGBP</td>
                        <td>18</td>
                        <td>58%</td>
                        <td>+$850.00</td>
                        <td>Running</td>
                    </tr>
                    <tr>
                        <td>BTCUSD</td>
                        <td>12</td>
                        <td>45%</td>
                        <td>-$125.00</td>
                        <td>Stopped</td>
                    </tr>
                </table>
            </div>
            
            <div class="footer">
                <p>TradeBot Hub v1.0.0 | Confidential</p>
            </div>
        </body>
        </html>
    `;
}

/**
 * Simulate real-time data updates (for demonstration)
 */
function simulateRealTimeUpdates() {
    setInterval(() => {
        broadcastMessage({
            type: 'metrics_update',
            timestamp: new Date().toISOString(),
            cpuUsage: (Math.random() * 80).toFixed(2),
            memoryUsage: (Math.random() * 60).toFixed(2),
            activeConnections: Math.floor(Math.random() * 100)
        });
    }, 5000);
}

// ===== Server Startup =====

function printStartupBanner() {
    console.log(`
╔════════════════════════════════════════════════════════════╗
║         TradeBot Hub - Backend Server v1.0.0              ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  🚀 Server running at http://localhost:${CURRENT_PORT}      ║
║  📡 WebSocket: ws://localhost:${CURRENT_PORT}              ║
║  🔌 FastAPI Backend: ${FASTAPI_URL}                        ║
║                                                            ║
║  Routes:                                                   ║
║    GET  /                           - Main dashboard       ║
║    GET  /api/system/status          - System info          ║
║    GET  /api/network/ip             - Local IP info        ║
║    GET  /api/bots                   - Bot status           ║
║    POST /api/bots/start             - Start bot            ║
║    POST /api/bots/stop              - Stop bot             ║
║    GET  /api/processes              - Process list         ║
║    POST /api/processes/:pid/kill    - Kill process         ║
║    POST /api/reports/generate       - Generate PDF report  ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
    `);
}

function startServer(initialPort) {
    CURRENT_PORT = initialPort;
    
    // On Windows, binding to 0.0.0.0 may require admin.
    // Try 0.0.0.0 first, fallback to undefined (all interfaces via OS)
    const HOST = process.platform === 'win32' ? undefined : '0.0.0.0';

    const onError = (err) => {
        if (err && err.code === 'EADDRINUSE') {
            const nextPort = CURRENT_PORT + 1;
            console.warn(`Port ${CURRENT_PORT} in use. Retrying on ${nextPort}...`);
            CURRENT_PORT = nextPort;
            // Retry listen on next port
            setTimeout(() => server.listen(CURRENT_PORT, HOST), 100);
        } else {
            console.error('Server failed to start:', err);
            process.exit(1);
        }
    };

    const onListening = () => {
        // Remove temporary error handler once listening succeeds
        server.off('error', onError);
        printStartupBanner();
        simulateRealTimeUpdates();
    };

    server.on('error', onError);
    server.once('listening', onListening);
    server.listen(CURRENT_PORT, HOST);
}

startServer(PORT);

// Graceful shutdown
process.on('SIGTERM', () => {
    console.log('SIGTERM received, closing server...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});

process.on('SIGINT', () => {
    console.log('SIGINT received, closing server...');
    server.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
});

module.exports = server;
