#!/bin/bash
# TradeBot Hub Frontend - Development Setup Script
# Run this script to set up the development environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed"
        echo "  Download from: https://nodejs.org/"
        exit 1
    fi
    print_success "Node.js $(node --version)"
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed"
        exit 1
    fi
    print_success "npm $(npm --version)"
    
    # Check if FastAPI backend is available
    print_info "Checking FastAPI backend..."
    if curl -s http://localhost:8000/docs > /dev/null 2>&1; then
        print_success "FastAPI backend is running"
    else
        print_warning "FastAPI backend is not running on http://localhost:8000"
        print_info "Start it with: python -m uvicorn app.main:app --reload"
    fi
    
    echo ""
}

# Install dependencies
install_dependencies() {
    print_header "Installing Dependencies"
    
    if [ ! -d "node_modules" ]; then
        print_info "Running npm install..."
        npm install
        print_success "Dependencies installed"
    else
        print_info "node_modules already exists"
        print_info "Running npm ci to ensure consistency..."
        npm ci
    fi
    
    echo ""
}

# Setup environment
setup_environment() {
    print_header "Setting Up Environment"
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            print_info "Creating .env from .env.example..."
            cp .env.example .env
            print_success ".env created"
            print_warning "Please review and update .env with your settings"
        fi
    else
        print_info ".env already exists"
    fi
    
    echo ""
}

# Create necessary directories
create_directories() {
    print_header "Creating Directories"
    
    directories=("logs" "public" "public/icons" "public/screenshots" "reports")
    
    for dir in "${directories[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_success "Created $dir/"
        else
            print_info "$dir/ already exists"
        fi
    done
    
    echo ""
}

# Test installation
test_installation() {
    print_header "Testing Installation"
    
    # Test imports
    print_info "Checking Node.js modules..."
    node -e "require('express'); console.log('✓ express')"
    node -e "require('ws'); console.log('✓ ws')"
    node -e "require('puppeteer'); console.log('✓ puppeteer')"
    
    print_success "All modules loaded successfully"
    echo ""
}

# Display next steps
print_next_steps() {
    print_header "Next Steps"
    
    echo ""
    echo "1. Start the frontend server:"
    echo -e "   ${YELLOW}npm start${NC}"
    echo ""
    echo "2. Open in browser:"
    echo -e "   ${YELLOW}http://localhost:3000${NC}"
    echo ""
    echo "3. Or access via local IP:"
    echo -e "   ${YELLOW}http://\$(hostname -I | awk '{print \$1}'):3000${NC}"
    echo ""
    echo "Optional: Install as PWA"
    echo "  - Open http://localhost:3000 in Chrome/Edge"
    echo "  - Click 'Install' button in address bar"
    echo ""
    echo "For more information, see:"
    echo "  - README.md - Full documentation"
    echo "  - QUICKSTART.md - Quick start guide"
    echo "  - config.js - Configuration options"
    echo ""
}

# Main execution
main() {
    clear
    
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║   TradeBot Hub Frontend - Development Setup               ║"
    echo "║                                                            ║"
    echo "║   This script will set up your development environment    ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo ""
    
    # Run setup steps
    check_prerequisites
    install_dependencies
    setup_environment
    create_directories
    test_installation
    print_next_steps
    
    print_header "Setup Complete!"
    echo ""
    print_success "Your development environment is ready!"
    echo ""
}

# Run main function
main
