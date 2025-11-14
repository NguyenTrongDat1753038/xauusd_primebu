# Multi-stage build for TradeBot Hub Frontend

# Stage 1: Build dependencies
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production && \
    npm cache clean --force

# Stage 2: Runtime
FROM node:18-alpine

# Install Chromium for Puppeteer PDF generation
RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-dejavu \
    dumb-init

WORKDIR /app

# Set environment variables
ENV NODE_ENV=production \
    PORT=3000 \
    FASTAPI_URL=http://fastapi:8000 \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser

# Copy from builder stage
COPY --from=builder /app/node_modules ./node_modules

# Copy application files
COPY server.js .
COPY index.html .
COPY app.js .
COPY sw.js .
COPY manifest.json .
COPY package.json .

# Create logs directory
RUN mkdir -p logs && \
    chmod 755 logs

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/api/system/status', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Use dumb-init to handle signals properly
ENTRYPOINT ["/usr/sbin/dumb-init", "--"]

# Start application
CMD ["node", "server.js"]
