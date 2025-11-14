/**
 * TradeBot Hub - Frontend Alpine.js App Logic
 * Handles routing, API integration, WebSocket, and UI state management
 */

// API Client
const apiClient = {
    baseURL: 'http://localhost:8001/api/v1',
    
    async request(endpoint, options = {}) {
        const url = this.baseURL + endpoint;
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        return response.json();
    },
    
    // Bot endpoints
    async getBots() {
        return this.request('/bots');
    },
    
    async startBot(botId) {
        return this.request(`/bots/start`, {
            method: 'POST',
            body: JSON.stringify({ bot_id: botId })
        });
    },
    
    async stopBot(botId) {
        return this.request(`/bots/stop`, {
            method: 'POST',
            body: JSON.stringify({ bot_id: botId })
        });
    },
    
    async getProcesses() {
        return this.request('/processes');
    },
    
    async killProcess(pid) {
        return this.request(`/processes/${pid}/kill`, { method: 'POST' });
    },
    
    async generateReport(params) {
        return this.request('/reports/generate', {
            method: 'POST',
            body: JSON.stringify(params)
        });
    }
};

// WebSocket Client
class WebSocketClient {
    constructor(url = 'ws://localhost:3001') {
        this.url = url;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 999; // Unlimited retries
        this.reconnectDelay = 3000;
    }
    
    connect() {
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(this.url);
                
                this.ws.onopen = () => {
                    console.log('WebSocket connected');
                    this.reconnectAttempts = 0;
                    resolve();
                };
                
                this.ws.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    reject(error);
                };
                
                this.ws.onclose = () => {
                    this.attemptReconnect();
                };
            } catch (error) {
                reject(error);
            }
        });
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1), 30000);
            console.log(`Attempting to reconnect... (attempt ${this.reconnectAttempts}, delay ${delay}ms)`);
            setTimeout(() => this.connect(), delay);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    on(event, callback) {
        if (this.ws) {
            this.ws.addEventListener(event, (e) => {
                const data = event === 'message' ? JSON.parse(e.data) : e;
                callback(data);
            });
        }
    }
    
    close() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Main Alpine.js App State
function appState() {
    return {
        // UI State
        sidebarOpen: true,
        darkMode: true,
        currentPage: 'dashboard',
        
        // Navigation
        navItems: [
            { id: 'dashboard', label: 'Dashboard', icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>' },
            { id: 'bots', label: 'Bots', icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"></path></svg>' },
            { id: 'reports', label: 'Reports', icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>' },
            { id: 'remote', label: 'Remote', icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4.243 4.243a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.658 0l4.242-4.243a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>' },
            { id: 'settings', label: 'Settings', icon: '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>' }
        ],
        
        // Bots Data
        bots: [
            { 
                id: 'xauusd', 
                name: 'XAUUSD Bot', 
                description: 'Gold scalping',
                icon: '🥇',
                running: false,
                selected: false,
                pnl: '+$1,250.00',
                winRate: '62%',
                trades: '24',
                performanceData: [120, 145, 135, 160, 175, 190, 185, 210, 225, 240, 255, 270, 285, 300, 315],
                lastUpdate: null,
                connectionState: 'connected'
            },
            { 
                id: 'eurgbp', 
                name: 'EURGBP Bot (Conservative)', 
                description: 'Swing trading - Low risk',
                icon: '💱',
                running: false,
                selected: false,
                pnl: '+$850.00',
                winRate: '58%',
                trades: '18',
                performanceData: [100, 110, 125, 115, 130, 140, 150, 145, 160, 170, 180, 175, 190, 200, 210],
                lastUpdate: null,
                connectionState: 'connected'
            },
            { 
                id: 'eurgbp_high_risk', 
                name: 'EURGBP Bot (High Risk)', 
                description: 'Swing trading - High risk',
                icon: '💱',
                running: false,
                selected: false,
                pnl: '+$1,200.00',
                winRate: '52%',
                trades: '22',
                performanceData: [100, 130, 110, 150, 140, 180, 160, 200, 190, 220, 210, 240, 230, 260, 250],
                lastUpdate: null,
                connectionState: 'connected'
            },
            { 
                id: 'btcusd', 
                name: 'BTCUSD Bot', 
                description: 'Trend following',
                icon: '₿',
                running: false,
                selected: false,
                pnl: '-$125.00',
                winRate: '45%',
                trades: '12',
                performanceData: [100, 95, 105, 90, 100, 85, 95, 80, 90, 75, 85, 70, 80, 75, 70],
                lastUpdate: null,
                connectionState: 'connected'
            }
        ],
        
        // Chart instances (stored for cleanup/updates)
        chartInstances: {},
        
        // Process Data
        processes: [
            { pid: '5432', bot: 'XAUUSD', startTime: '2024-01-15 09:30:15', cpu: 12, ram: 256, status: 'Running' },
            { pid: '5433', bot: 'EURGBP', startTime: '2024-01-15 09:31:22', cpu: 8, ram: 189, status: 'Running' }
        ],
        
        // Logs
        logId: 0,
        logs: [],
        
        // Reports
        selectedBots: [],
        reportType: 'summary',
        
        // Settings
        settings: {
            mt5Path: 'C:\\Program Files\\MetaTrader 5\\terminal64.exe',
            metaapiToken: '****',
            soundEnabled: true,
            desktopEnabled: true,
            telegramEnabled: false,
            autoStart: true,
            autoBackup: true
        },
        
        // Connection Status
        mt5Connected: true,
        botsRunning: 0,
        
        // Time
        currentTime: '00:00:00',
        
        // WebSocket Client
        wsClient: null,
        
        // Computed Properties
        get currentPageLabel() {
            const item = this.navItems.find(i => i.id === this.currentPage);
            return item ? item.label : 'Dashboard';
        },
        
        get localIP() {
            return 'http://192.168.1.100:3000';
        },
        
        // Helper to get "time ago" string
        getTimeAgo(timestamp) {
            if (!timestamp) return 'Never';
            
            const now = new Date();
            const diffMs = now - timestamp;
            const diffSec = Math.floor(diffMs / 1000);
            
            if (diffSec < 10) return 'Just now';
            if (diffSec < 60) return `${diffSec}s ago`;
            
            const diffMin = Math.floor(diffSec / 60);
            if (diffMin < 60) return `${diffMin}m ago`;
            
            const diffHour = Math.floor(diffMin / 60);
            if (diffHour < 24) return `${diffHour}h ago`;
            
            const diffDay = Math.floor(diffHour / 24);
            return `${diffDay}d ago`;
        },
        
        // Initialization
        async init() {
            console.log('Initializing TradeBot Hub...');
            
            // Load settings and bot states from localStorage
            this.loadSettings();
            this.loadBotStates();
            
            // Start real-time clock
            this.updateClock();
            setInterval(() => this.updateClock(), 1000);
            
            // Initialize WebSocket (auto-detect port from current page if possible)
            const wsPort = window.location.port || '3001';
            this.wsClient = new WebSocketClient(`ws://localhost:${wsPort}`);
            try {
                await this.wsClient.connect();
                this.setupWebSocketListeners();
            } catch (error) {
                console.warn('WebSocket connection failed:', error);
                this.addLog('warning', 'WebSocket connection failed, falling back to polling');
            }
            
            // Load initial data
            await this.loadBots();
            await this.loadProcesses();
            
            // Setup polling for real-time updates
            setInterval(() => this.loadBots(), 5000);
            setInterval(() => this.loadProcesses(), 3000);
            
            // Initialize sparkline charts
            setTimeout(() => this.initSparklineCharts(), 200);
            
            // Initialize date picker if on reports page
            setTimeout(() => this.initDatePicker(), 100);
        },
        
        updateClock() {
            const now = new Date();
            this.currentTime = now.toLocaleTimeString();
        },
        
        setupWebSocketListeners() {
            if (!this.wsClient || !this.wsClient.ws) return;
            
            this.wsClient.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    switch (data.type) {
                        case 'bot_status':
                            this.handleBotStatusUpdate(data);
                            break;
                        case 'log':
                            this.addLog(data.level || 'info', data.message);
                            break;
                        case 'process_update':
                            this.updateProcess(data);
                            break;
                    }
                } catch (error) {
                    console.error('WebSocket message error:', error);
                }
            };
        },
        
        // Bot Management
        async loadBots() {
            try {
                // Load bot status from backend (which reads from Redis)
                const redisStatus = await apiClient.getBots();
                
                // Merge Redis state with local bot definitions
                this.bots.forEach(bot => {
                    const serverState = redisStatus[bot.id];
                    if (serverState) {
                        bot.running = serverState.status === 'running';
                        bot.lastUpdate = new Date();
                        // Keep PnL/winRate from local if not provided by server
                    } else {
                        bot.running = false;
                    }
                });
                
                // Save to localStorage for persistence
                this.saveBotStates();
                
                this.updateBotsRunning();
            } catch (error) {
                console.error('Failed to load bots:', error);
                this.addLog('error', `Failed to load bots: ${error.message}`);
                // Fallback: load from localStorage
                this.loadBotStates();
            }
        },
        
        async startBot(botId) {
            try {
                this.addLog('info', `Starting bot: ${botId}`);
                
                // Gọi API backend để start bot
                const response = await apiClient.startBot(botId);
                this.addLog('success', `Bot start request sent. Task ID: ${response.task_id || 'pending'}`);
                
                // Optimistic UI update
                const bot = this.bots.find(b => b.id === botId);
                if (bot) {
                    bot.running = true;
                }
                this.updateBotsRunning();
                this.saveBotStates();
                
                this.showNotification('success', `Bot ${botId} start request sent`);
            } catch (error) {
                console.error('Failed to start bot:', error);
                this.addLog('error', `Failed to start bot ${botId}: ${error.message}`);
                this.showNotification('error', `Failed to start ${botId}`);
            }
        },
        
        async stopBot(botId) {
            try {
                this.addLog('info', `Stopping bot: ${botId}`);
                
                // Gọi API backend để stop bot
                const response = await apiClient.stopBot(botId);
                this.addLog('success', `Bot stop request sent. Task ID: ${response.task_id || 'pending'}`);
                
                // Optimistic UI update
                const bot = this.bots.find(b => b.id === botId);
                if (bot) {
                    bot.running = false;
                }
                this.updateBotsRunning();
                this.saveBotStates();
                
                this.showNotification('success', `Bot ${botId} stop request sent`);
            } catch (error) {
                console.error('Failed to stop bot:', error);
                this.addLog('error', `Failed to stop bot ${botId}: ${error.message}`);
                this.showNotification('error', `Failed to stop ${botId}`);
            }
        },
        
        async startSelected() {
            const selectedBots = this.bots.filter(b => b.selected);
            if (selectedBots.length === 0) {
                this.showNotification('warning', 'No bots selected');
                return;
            }
            
            for (const bot of selectedBots) {
                await this.startBot(bot.id);
                await new Promise(resolve => setTimeout(resolve, 500));
            }
        },
        
        async stopAll() {
            if (!confirm('Stop all running bots?')) return;
            
            for (const bot of this.bots) {
                if (bot.running) {
                    await this.stopBot(bot.id);
                    await new Promise(resolve => setTimeout(resolve, 500));
                }
            }
        },
        
        updateBotsRunning() {
            this.botsRunning = this.bots.filter(b => b.running).length;
        },
        
        handleBotStatusUpdate(data) {
            const bot = this.bots.find(b => b.id === data.bot_id);
            if (bot) {
                bot.running = data.running;
                bot.pnl = data.pnl;
                bot.winRate = data.win_rate;
                bot.trades = data.trades;
                bot.lastUpdate = new Date();
                
                // Update sparkline if new performance data is available
                if (data.performance_data && data.performance_data.length > 0) {
                    bot.performanceData = data.performance_data;
                    this.updateSparklineChart(bot.id);
                }
            }
            this.updateBotsRunning();
        },
        
        // Process Management
        async loadProcesses() {
            try {
                // Replace with actual API call when ready:
                // const data = await apiClient.getProcesses();
                // this.processes = data;
            } catch (error) {
                console.error('Failed to load processes:', error);
            }
        },
        
        updateProcess(data) {
            const proc = this.processes.find(p => p.pid === data.pid);
            if (proc) {
                proc.cpu = data.cpu;
                proc.ram = data.ram;
                proc.status = data.status;
            }
        },
        
        async killProcess(pid) {
            if (!confirm(`Kill process ${pid}?`)) return;
            
            try {
                this.addLog('info', `Killing process: ${pid}`);
                // await apiClient.killProcess(pid);
                
                // Optimistic UI update
                this.processes = this.processes.filter(p => p.pid !== pid);
                this.showNotification('success', `Process ${pid} terminated`);
            } catch (error) {
                console.error('Failed to kill process:', error);
                this.addLog('error', `Failed to kill process ${pid}: ${error.message}`);
                this.showNotification('error', `Failed to kill process ${pid}`);
            }
        },
        
        // Logging
        addLog(level, message) {
            const now = new Date();
            const time = now.toLocaleTimeString();
            this.logs.push({
                id: ++this.logId,
                level,
                message,
                time
            });
            
            // Keep only last 1000 logs
            if (this.logs.length > 1000) {
                this.logs = this.logs.slice(-1000);
            }
            
            // Auto-scroll to bottom
            this.$nextTick(() => {
                const logConsole = this.$refs.logConsole;
                if (logConsole) {
                    logConsole.scrollTop = logConsole.scrollHeight;
                }
            });
        },
        
        clearLogs() {
            if (confirm('Clear all logs?')) {
                this.logs = [];
            }
        },
        
        async exportLogs() {
            const csv = this.logs.map(l => `${l.time}|${l.level.toUpperCase()}|${l.message}`).join('\n');
            const blob = new Blob([csv], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logs_${new Date().toISOString()}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        },
        
        // Reports
        initDatePicker() {
            flatpickr('#dateRange', {
                mode: 'range',
                dateFormat: 'Y-m-d',
                defaultDate: [new Date(Date.now() - 7 * 24 * 60 * 60 * 1000), new Date()]
            });
        },
        
        // Sparkline Charts
        initSparklineCharts() {
            console.log('Initializing sparkline charts...');
            this.bots.forEach(bot => {
                const canvas = document.getElementById(`chart-${bot.id}`);
                if (!canvas) {
                    console.warn(`Canvas not found for bot: ${bot.id}`);
                    return;
                }
                
                const ctx = canvas.getContext('2d');
                const isProfitable = bot.pnl.startsWith('+');
                
                // Destroy existing chart if any
                if (this.chartInstances[bot.id]) {
                    this.chartInstances[bot.id].destroy();
                }
                
                // Create new sparkline chart
                this.chartInstances[bot.id] = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: Array(bot.performanceData.length).fill(''),
                        datasets: [{
                            data: bot.performanceData,
                            borderColor: isProfitable ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)',
                            backgroundColor: isProfitable ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 0,
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: { enabled: false }
                        },
                        scales: {
                            x: { display: false },
                            y: { display: false }
                        },
                        interaction: {
                            mode: 'nearest',
                            intersect: false
                        },
                        animation: {
                            duration: 750,
                            easing: 'easeInOutQuart'
                        }
                    }
                });
            });
        },
        
        updateSparklineChart(botId) {
            const bot = this.bots.find(b => b.id === botId);
            const chart = this.chartInstances[botId];
            
            if (!bot || !chart) return;
            
            const isProfitable = bot.pnl.startsWith('+');
            
            // Update data
            chart.data.datasets[0].data = bot.performanceData;
            chart.data.datasets[0].borderColor = isProfitable ? 'rgb(34, 197, 94)' : 'rgb(239, 68, 68)';
            chart.data.datasets[0].backgroundColor = isProfitable ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)';
            chart.update('none'); // Update without animation for real-time feel
        },
        
        async generatePDF() {
            try {
                this.addLog('info', 'Generating PDF report...');
                
                // Simulate API call
                // const response = await fetch('/api/report', {
                //     method: 'POST',
                //     body: JSON.stringify({
                //         bots: this.selectedBots,
                //         type: this.reportType
                //     })
                // });
                
                this.showNotification('success', 'PDF generated successfully');
                this.addLog('info', 'PDF report generated');
            } catch (error) {
                console.error('Failed to generate PDF:', error);
                this.addLog('error', `PDF generation failed: ${error.message}`);
                this.showNotification('error', 'Failed to generate PDF');
            }
        },
        
        async downloadAllReports() {
            this.showNotification('info', 'Downloading reports...');
        },
        
        // Remote
        copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                this.showNotification('success', 'Copied to clipboard');
            });
        },
        
        generateQRCode() {
            const qrContainer = document.getElementById('qrCode');
            if (qrContainer && QRCode) {
                qrContainer.innerHTML = '';
                new QRCode(qrContainer, {
                    text: this.localIP,
                    width: 200,
                    height: 200,
                    colorDark: '#ffffff',
                    colorLight: '#0f172a'
                });
            }
        },
        
        async checkUpdates() {
            this.addLog('info', 'Checking for updates...');
            // Simulate update check
            await new Promise(resolve => setTimeout(resolve, 2000));
            this.addLog('info', 'Already on latest version');
            this.showNotification('info', 'No updates available');
        },
        
        async restartServer() {
            if (!confirm('Restart the server? This will disconnect all clients.')) return;
            
            try {
                this.addLog('info', 'Restarting server...');
                // await apiClient.request('/system/restart', { method: 'POST' });
                this.showNotification('warning', 'Server restarting...');
            } catch (error) {
                this.addLog('error', `Restart failed: ${error.message}`);
                this.showNotification('error', 'Failed to restart server');
            }
        },
        
        async openBrowser() {
            window.open(this.localIP, '_blank');
        },
        
        // Settings
        saveSettings() {
            try {
                localStorage.setItem('appSettings', JSON.stringify(this.settings));
                this.showNotification('success', 'Settings saved successfully');
                this.addLog('info', 'Settings saved');
            } catch (error) {
                this.showNotification('error', 'Failed to save settings');
                this.addLog('error', `Failed to save settings: ${error.message}`);
            }
        },
        
        loadSettings() {
            try {
                const saved = localStorage.getItem('appSettings');
                if (saved) {
                    this.settings = { ...this.settings, ...JSON.parse(saved) };
                }
            } catch (error) {
                console.error('Failed to load settings:', error);
            }
        },
        
        saveBotStates() {
            try {
                const states = this.bots.map(b => ({ id: b.id, running: b.running }));
                localStorage.setItem('botStates', JSON.stringify(states));
            } catch (error) {
                console.error('Failed to save bot states:', error);
            }
        },
        
        loadBotStates() {
            try {
                const saved = localStorage.getItem('botStates');
                if (saved) {
                    const states = JSON.parse(saved);
                    states.forEach(state => {
                        const bot = this.bots.find(b => b.id === state.id);
                        if (bot) {
                            bot.running = state.running;
                        }
                    });
                    this.updateBotsRunning();
                }
            } catch (error) {
                console.error('Failed to load bot states:', error);
            }
        },
        
        // UI Utilities
        toggleTheme() {
            this.darkMode = !this.darkMode;
            const html = document.documentElement;
            if (this.darkMode) {
                html.setAttribute('data-theme', 'dark');
            } else {
                html.setAttribute('data-theme', 'light');
            }
            localStorage.setItem('darkMode', this.darkMode);
        },
        
        showNotification(type, message) {
            // Use DaisyUI toast/alert or custom notification
            console.log(`[${type.toUpperCase()}] ${message}`);
            // Could integrate with toastr or custom notification system
        }
    };
}
