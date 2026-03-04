#!/bin/bash

# Aletheia Full Stack Development Script
# Starts backend + web frontend (new UI)

set -e

echo "========================================"
echo "  Aletheia - Truth Engine"
echo "  Full Stack Development Environment"
echo "========================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project paths
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="${SCRIPT_DIR}/aletheia-backend"
WEB_DIR="${SCRIPT_DIR}/frontend"
BACKEND_PORT="8000"
WEB_PORT="5173"

port_busy() {
    local port="$1"
    if command_exists ss; then
        ss -ltn 2>/dev/null | grep -q ":${port} " && return 0 || return 1
    fi
    return 1
}

backend_has_required_routes() {
    local port="$1"
    local result
    result=$(curl -s "http://127.0.0.1:${port}/openapi.json" 2>/dev/null | python3 -c "import sys,json
try:
 d=json.load(sys.stdin)
 ok='/api/v1/multiplatform/playwright-orchestrate' in d.get('paths',{}) and '/api/v1/reports/export' in d.get('paths',{})
 print('1' if ok else '0')
except Exception:
 print('0')")
    [ "$result" = "1" ]
}

pick_backend_port() {
    local preferred=(8000 8001 8010 8100)
    for p in "${preferred[@]}"; do
        if port_busy "$p"; then
            if backend_has_required_routes "$p"; then
                BACKEND_PORT="$p"
                echo -e "${GREEN}Backend already running on http://localhost:${BACKEND_PORT} (new routes detected)${NC}"
                return 0
            fi
            continue
        fi
        BACKEND_PORT="$p"
        return 1
    done
    BACKEND_PORT="8010"
    return 1
}

pick_web_port() {
    local preferred=(5173 5174 5175 5176 5177 5180)
    for p in "${preferred[@]}"; do
        if ! port_busy "$p"; then
            WEB_PORT="$p"
            return 0
        fi
    done
    WEB_PORT="5180"
    return 0
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to start backend
start_backend() {
    echo -e "\n${YELLOW}Starting Backend Server...${NC}"
    
    if [ ! -d "$BACKEND_DIR" ]; then
        echo -e "${RED}Backend directory not found: $BACKEND_DIR${NC}"
        exit 1
    fi
    
    cd "$BACKEND_DIR"
    
    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        echo -e "${RED}Virtual environment not found. Creating...${NC}"
        python3 -m venv venv
        source venv/bin/activate
        pip install -r requirements.txt
    fi
    
    if pick_backend_port; then
        return
    fi

    local candidate_ports=("$BACKEND_PORT" 8001 8010 8100)
    local started=0
    for p in "${candidate_ports[@]}"; do
        echo -e "${YELLOW}Trying backend port ${p}...${NC}"
        uvicorn main:app --reload --host 0.0.0.0 --port "${p}" >/tmp/aletheia_backend_start.log 2>&1 &
        BACKEND_PID=$!
        sleep 2
        if kill -0 "$BACKEND_PID" 2>/dev/null; then
            BACKEND_PORT="$p"
            started=1
            echo -e "${GREEN}Backend starting on http://localhost:${BACKEND_PORT}${NC}"
            echo "Backend PID: $BACKEND_PID"
            break
        fi
    done

    if [ "$started" -ne 1 ]; then
        echo -e "${RED}Failed to start backend on candidate ports.${NC}"
        if [ -f /tmp/aletheia_backend_start.log ]; then
            cat /tmp/aletheia_backend_start.log
        fi
        exit 1
    fi
}

# Function to start web frontend
start_web() {
    echo -e "\n${YELLOW}Starting Web Frontend...${NC}"
    
    if [ ! -d "$WEB_DIR" ]; then
        echo -e "${RED}Web directory not found: $WEB_DIR${NC}"
        exit 1
    fi
    
    cd "$WEB_DIR"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        npm install
    fi
    
    pick_web_port
    echo -e "${GREEN}Web app starting on http://localhost:${WEB_PORT}${NC}"
    echo -e "${GREEN}Using backend: http://localhost:${BACKEND_PORT}/api/v1${NC}"
    VITE_API_BASE_URL="http://localhost:${BACKEND_PORT}/api/v1" npm run dev -- --host 0.0.0.0 --port "${WEB_PORT}" --strictPort
}

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Goodbye!${NC}"
}

# Set trap for cleanup
trap cleanup EXIT

# Main execution
case "${1:-all}" in
    backend)
        start_backend
        wait
        ;;
    web)
        start_web
        ;;
    all)
        start_backend
        sleep 3  # Wait for backend to start
        start_web
        ;;
    *)
        echo "Usage: $0 {backend|web|all}"
        echo "  backend - Start only the backend server"
        echo "  web     - Start only the web app"
        echo "  all     - Start both (default)"
        exit 1
        ;;
esac
