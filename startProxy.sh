#!/bin/bash
# startPrxy.sh - Start Orchestration Controller with Hypercorn

set -e  # Exit on error

# ============================================================
# CONFIGURATION
# ============================================================

export BASE_DIR=/u01/app/ssaAgent/orchestration-system
LOG_DIR="$BASE_DIR/logs"

# Script paths
export SCRIPTS_BASE_PATH=$BASE_DIR/scripts

# Port configuration (auto-detect if 7604 is in use)
if netstat -an | grep -q "7585.*LISTEN"; then
    export PORT=7584
else
    export PORT=7585
fi

export PORT=7585

# Ensure logs directory exists
mkdir -p "$LOG_DIR"

echo "=========================================="
echo "Orchestration Controller Startup"
echo "=========================================="
echo "Base Directory : $BASE_DIR"
echo "Logs Directory : $LOG_DIR"
echo "Port           : $PORT"
echo "Controller URL : $CONTROLLER_URL"
echo ""

# ============================================================
# STOP OLD PROCESSES
# ============================================================

echo "[1/3] Stopping old processes..."
pkill -f "python.*proxy.py" 2>/dev/null || true
sleep 2
echo "✅ Old processes stopped"
echo ""

# ============================================================
# VERIFY SSL CERTIFICATES
# ============================================================

echo "[2/3] Checking SSL certificates..."

if [ ! -f "${BASE_DIR}/controller/certs/cert.pem" ]; then
    echo "❌ Server certificate not found: ${BASE_DIR}/controller/certs/cert.pem"
    exit 1
fi

if [ ! -f "${BASE_DIR}/controller/certs/key.pem" ]; then
    echo "❌ Server key not found: ${BASE_DIR}/controller/certs/key.pem"
    exit 1
fi

if [ ! -f "${BASE_DIR}/controller/certs/certChain.pem" ]; then
    echo "❌ CA certificate not found: ${BASE_DIR}/controller/certs/certChain.pem"
    exit 1
fi

echo "✅ Server certificate: ${BASE_DIR}/controller/certs/cert.pem"
echo "✅ Server key:         ${BASE_DIR}/controller/certs/key.pem"
echo "✅ CA certificate:     ${BASE_DIR}/controller/certs/certChain.pem"
echo ""

# ============================================================
# ============================================================

# ============================================================
# ============================================================

echo "[3/3] Starting Hypercorn server..."
echo ""
echo "=========================================="
echo "  Hypercorn HTTPS Server"
echo "=========================================="
echo "Host: 10.28.203.100"
echo "Port: $PORT"
echo "Auth: Client Certificate (Smartcard)"
echo "=========================================="
echo ""
echo "✅ Access at: $CONTROLLER_URL/login.html"
echo ""
echo "⚠️  Use HTTPS (not HTTP)!"
echo "⚠️  Use Hypercorn (not Uvicorn)!"
echo ""
echo "=========================================="
echo ""
echo "Starting server..."
echo ""

# Start Proxy with SSL key logging for debugging (optional)
# Remove SSLKEYLOGFILE for production
nohup python $BASE_DIR/proxy/ssl_proxy.py  >>  "$LOG_DIR/proxy.log" 2>&1 &
