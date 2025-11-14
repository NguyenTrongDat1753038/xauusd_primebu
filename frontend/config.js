/**
 * TradeBot Hub Frontend - Configuration Guide
 * 
 * This file documents all configuration options and how to customize the app
 */

// ========================================
// 1. SERVER CONFIGURATION
// ========================================

// Environment variables (in .env or system environment):

const serverConfig = {
  // HTTP Server
  PORT: process.env.PORT || 3000,
  HOST: process.env.HOST || 'localhost',
  NODE_ENV: process.env.NODE_ENV || 'development',
  
  // Backend Integration
  FASTAPI_URL: process.env.FASTAPI_URL || 'http://localhost:8000',
  FASTAPI_TIMEOUT: parseInt(process.env.FASTAPI_TIMEOUT) || 30000,
  
  // Redis
  REDIS_URL: process.env.REDIS_URL || 'redis://localhost:6379/0',
  
  // Security
  CORS_ORIGIN: process.env.CORS_ORIGIN || '*',
  SESSION_SECRET: process.env.SESSION_SECRET || 'development-secret',
  JWT_SECRET: process.env.JWT_SECRET || 'development-jwt-secret',
  
  // Logging
  LOG_LEVEL: process.env.LOG_LEVEL || 'info',
  LOG_DIR: process.env.LOG_DIR || './logs',
  
  // Features
  ENABLE_PDF_GENERATION: process.env.ENABLE_PDF_GENERATION !== 'false',
  ENABLE_PUSH_NOTIFICATIONS: process.env.ENABLE_PUSH_NOTIFICATIONS !== 'false',
  ENABLE_SERVICE_WORKER: process.env.ENABLE_SERVICE_WORKER !== 'false',
  ENABLE_OFFLINE_SUPPORT: process.env.ENABLE_OFFLINE_SUPPORT !== 'false'
};

// ========================================
// 2. FRONTEND CONFIGURATION
// ========================================

const frontendConfig = {
  // UI Theme
  DEFAULT_THEME: 'dark', // 'dark' or 'light'
  PRIMARY_COLOR: '#00c853',
  ACCENT_COLOR: '#00bcd4',
  
  // Layout
  SIDEBAR_DEFAULT_OPEN: true,
  SIDEBAR_WIDTH_OPEN: '288px',    // w-72 in Tailwind
  SIDEBAR_WIDTH_CLOSED: '80px',   // w-20 in Tailwind
  
  // Dashboard
  BOT_CARD_LAYOUT: 'grid', // 'grid' or 'list'
  BOT_CARDS_PER_ROW: 3,    // for md: 2, lg: 3
  CHART_REFRESH_INTERVAL: 5000, // 5 seconds
  METRICS_PRECISION: 2,     // decimal places
  
  // Real-time Updates
  POLLING_INTERVAL: 5000,   // fallback if WebSocket fails
  WEBSOCKET_RECONNECT_ATTEMPTS: 5,
  WEBSOCKET_RECONNECT_DELAY: 3000,
  
  // Forms
  FORM_VALIDATION: true,
  FORM_AUTO_SAVE: false,
  
  // Notifications
  SHOW_TOAST_NOTIFICATIONS: true,
  TOAST_DURATION: 3000,
  SOUND_ALERTS: true
};

// ========================================
// 3. API CONFIGURATION
// ========================================

const apiConfig = {
  // Endpoints
  endpoints: {
    BOTS: '/api/bots',
    PROCESSES: '/api/processes',
    SYSTEM_STATUS: '/api/system/status',
    NETWORK_IP: '/api/network/ip',
    REPORTS: '/api/reports',
    LOGS: '/api/logs',
    SETTINGS: '/api/settings'
  },
  
  // Timeouts (ms)
  REQUEST_TIMEOUT: 30000,
  STREAMING_TIMEOUT: 60000,
  
  // Retries
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000,
  
  // Caching
  CACHE_ENABLED: true,
  CACHE_DURATION: {
    SYSTEM_STATUS: 60000,   // 1 minute
    PROCESSES: 30000,       // 30 seconds
    BOTS: 10000,            // 10 seconds
    SETTINGS: 300000        // 5 minutes
  }
};

// ========================================
// 4. WEBSOCKET CONFIGURATION
// ========================================

const wsConfig = {
  // Connection
  URL: process.env.WS_URL || 'ws://localhost:3000',
  RECONNECT_ENABLED: true,
  MAX_RECONNECT_ATTEMPTS: 5,
  RECONNECT_INTERVAL: 3000,
  PING_INTERVAL: 30000,
  PING_TIMEOUT: 5000,
  
  // Limits
  MAX_MESSAGE_SIZE: 1024 * 1024, // 1MB
  MAX_CONNECTIONS: 100,
  
  // Message Types
  MESSAGE_TYPES: {
    CONNECTION: 'connection',
    BOT_STATUS: 'bot_status',
    LOG: 'log',
    PROCESS_UPDATE: 'process_update',
    METRICS: 'metrics_update',
    NOTIFICATION: 'notification'
  }
};

// ========================================
// 5. PDF GENERATION CONFIGURATION
// ========================================

const pdfConfig = {
  // Puppeteer
  HEADLESS: true,
  TIMEOUT: 30000,
  
  // PDF Options
  FORMAT: 'A4',
  ORIENTATION: 'portrait',
  MARGINS: {
    top: '20px',
    right: '20px',
    bottom: '20px',
    left: '20px'
  },
  
  // Content
  INCLUDE_HEADER: true,
  INCLUDE_FOOTER: true,
  INCLUDE_CHARTS: true,
  INCLUDE_TRADES_TABLE: true,
  
  // File naming
  FILENAME_FORMAT: 'report_{{botName}}_{{date}}.pdf', // e.g., report_XAUUSD_2024-01-15.pdf
  
  // Directory
  OUTPUT_DIR: './reports',
  MAX_SIZE_MB: 50
};

// ========================================
// 6. STORAGE CONFIGURATION
// ========================================

const storageConfig = {
  // LocalStorage Keys
  STORAGE_PREFIX: 'tradebot_',
  
  // Persistence
  PERSIST_SETTINGS: true,
  PERSIST_LAYOUT: true,
  PERSIST_FAVORITES: true,
  
  // Cache
  CACHE_STRATEGY: 'network-first', // 'cache-first', 'network-first', 'stale-while-revalidate'
  CACHE_VERSION: 'v1',
  
  // IndexedDB
  DB_NAME: 'TradeBot Hub',
  DB_VERSION: 1,
  OBJECT_STORES: {
    LOGS: 'logs',
    REPORTS: 'reports',
    SETTINGS: 'settings',
    CACHE: 'cache'
  }
};

// ========================================
// 7. BOT MANAGEMENT CONFIGURATION
// ========================================

const botConfig = {
  // Available Bots
  AVAILABLE_BOTS: [
    {
      id: 'xauusd',
      name: 'XAUUSD Bot',
      description: 'Gold scalping strategy',
      icon: '🥇',
      symbol: 'XAUUSD',
      timeframe: 'M1',
      strategy: 'scalping'
    },
    {
      id: 'eurgbp',
      name: 'EURGBP Bot (Conservative)',
      description: 'Swing trading - Low risk',
      icon: '💱',
      symbol: 'EURGBP',
      timeframe: 'H1',
      strategy: 'swing',
      configFile: 'eurgbp_prod.json'
    },
    {
      id: 'eurgbp_high_risk',
      name: 'EURGBP Bot (High Risk)',
      description: 'Swing trading - High risk',
      icon: '💱',
      symbol: 'EURGBP',
      timeframe: 'H1',
      strategy: 'swing',
      configFile: 'eurgbp_prod_high_risk.json'
    },
    {
      id: 'btcusd',
      name: 'BTCUSD Bot',
      description: 'Trend following strategy',
      icon: '₿',
      symbol: 'BTCUSD',
      timeframe: 'H4',
      strategy: 'trend'
    }
  ],
  
  // Operations
  START_TIMEOUT: 5000,
  STOP_TIMEOUT: 3000,
  HEALTH_CHECK_INTERVAL: 10000,
  
  // Limits
  MAX_CONCURRENT_BOTS: 3,
  MIN_RESTART_INTERVAL: 30000, // 30 seconds between restarts
  
  // Monitoring
  TRACK_PID: true,
  TRACK_MEMORY: true,
  TRACK_CPU: true,
  CPU_THRESHOLD: 80, // Alert if CPU > 80%
  MEMORY_THRESHOLD: 1024 // Alert if memory > 1GB
};

// ========================================
// 8. UI CUSTOMIZATION
// ========================================

const uiConfig = {
  // Colors
  colors: {
    primary: '#00c853',    // Success green
    secondary: '#00bcd4',  // Cyan
    success: '#00c853',
    error: '#ff5252',
    warning: '#ffd600',
    info: '#00bcd4',
    danger: '#ff1744'
  },
  
  // Page Sizes
  pagination: {
    DEFAULT_PAGE_SIZE: 10,
    PAGE_SIZES: [5, 10, 25, 50, 100]
  },
  
  // Date Format
  DATE_FORMAT: 'YYYY-MM-DD',
  TIME_FORMAT: 'HH:mm:ss',
  DATETIME_FORMAT: 'YYYY-MM-DD HH:mm:ss',
  
  // Numbers
  DECIMAL_PLACES: {
    PRICE: 2,
    VOLUME: 0,
    PERCENTAGE: 2,
    PROFIT_LOSS: 2
  },
  
  // Table Settings
  TABLE: {
    ROWS_PER_PAGE: 10,
    ENABLE_SORT: true,
    ENABLE_FILTER: true,
    ENABLE_EXPORT: true,
    STICKY_HEADER: true
  },
  
  // Modal Settings
  MODAL: {
    ANIMATION: true,
    CLOSE_ON_ESCAPE: true,
    CLOSE_ON_BACKDROP: true,
    FOCUS_TRAP: true
  }
};

// ========================================
// 9. PERFORMANCE OPTIMIZATION
// ========================================

const performanceConfig = {
  // Compression
  ENABLE_GZIP: true,
  ENABLE_BROTLI: true,
  
  // Caching
  CACHE_MAX_AGE: {
    HTML: '1h',
    JS_CSS: '1d',
    IMAGES: '7d',
    FONTS: '30d'
  },
  
  // Code Splitting
  ENABLE_CODE_SPLITTING: true,
  LAZY_LOAD_CHARTS: true,
  
  // Bundle Size
  MINIFY_JS: true,
  MINIFY_CSS: true,
  MINIFY_HTML: true,
  
  // API Optimization
  BATCH_REQUESTS: true,
  DEBOUNCE_SEARCH: 300, // ms
  DEBOUNCE_RESIZE: 150   // ms
};

// ========================================
// 10. SECURITY CONFIGURATION
// ========================================

const securityConfig = {
  // HTTPS
  FORCE_HTTPS: false, // Set to true in production
  HSTS_ENABLED: false,
  HSTS_MAX_AGE: 31536000,
  
  // CORS
  CORS_ENABLED: true,
  CORS_CREDENTIALS: false,
  
  // CSP (Content Security Policy)
  CSP_ENABLED: false, // Enable in production
  
  // Rate Limiting
  RATE_LIMIT_ENABLED: true,
  RATE_LIMIT_REQUESTS: 100,
  RATE_LIMIT_WINDOW: 60000, // 1 minute
  
  // Session
  SESSION_TIMEOUT: 3600000, // 1 hour
  REFRESH_TOKEN_LIFETIME: 604800000, // 7 days
  
  // Password Policy
  MIN_PASSWORD_LENGTH: 8,
  REQUIRE_SPECIAL_CHARS: false,
  REQUIRE_NUMBERS: false,
  REQUIRE_UPPERCASE: false
};

// ========================================
// 11. DEVELOPMENT CONFIGURATION
// ========================================

const devConfig = {
  // Debug Mode
  DEBUG: process.env.DEBUG === 'true',
  DEBUG_LEVEL: 'verbose', // 'silent', 'error', 'warn', 'info', 'verbose'
  
  // Logging
  LOG_API_CALLS: true,
  LOG_WEBSOCKET: true,
  LOG_STORAGE: true,
  
  // Mock Data
  USE_MOCK_DATA: false,
  MOCK_DELAY: 500, // ms
  
  // Feature Flags
  FEATURE_FLAGS: {
    EXPERIMENTAL_CHARTS: false,
    EXPERIMENTAL_REPORTS: false,
    NEW_DASHBOARD_LAYOUT: false
  }
};

// ========================================
// EXPORT CONFIGURATION
// ========================================

module.exports = {
  serverConfig,
  frontendConfig,
  apiConfig,
  wsConfig,
  pdfConfig,
  storageConfig,
  botConfig,
  uiConfig,
  performanceConfig,
  securityConfig,
  devConfig
};

// ========================================
// USAGE IN CODE
// ========================================

/*
// In app.js or server.js:
import { serverConfig, frontendConfig, botConfig } from './config.js';

// Access configuration
console.log(frontendConfig.DEFAULT_THEME);
console.log(botConfig.AVAILABLE_BOTS);
console.log(serverConfig.FASTAPI_URL);

// Override at runtime
process.env.PORT = 4000;
process.env.NODE_ENV = 'production';
*/

// ========================================
// ENVIRONMENT-SPECIFIC CONFIGURATION
// ========================================

/*
// .env.development
PORT=3000
NODE_ENV=development
FASTAPI_URL=http://localhost:8000
LOG_LEVEL=verbose
DEBUG=true
ENABLE_PDF_GENERATION=true

// .env.production
PORT=80
NODE_ENV=production
FASTAPI_URL=https://api.tradebot.com
LOG_LEVEL=info
DEBUG=false
FORCE_HTTPS=true
CSP_ENABLED=true
SESSION_TIMEOUT=3600000

// .env.docker
PORT=3000
NODE_ENV=production
FASTAPI_URL=http://fastapi:8000
REDIS_URL=redis://redis:6379/0
*/
