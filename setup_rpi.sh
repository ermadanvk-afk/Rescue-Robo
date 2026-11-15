#!/usr/bin/env bash
# ==============================================================================
# AI Search & Rescue Robot — Automated Setup Script for Raspberry Pi 5
# ==============================================================================
set -e

echo "=================================================="
echo "  RESCUE ROBOT PI 5 — ENVIRONMENT SETUP           "
echo "=================================================="

# 1. Update APT and install system libraries
echo "[1/5] Installing Raspberry Pi OS system packages..."
sudo apt update
sudo apt install -y \
    python3-picamera2 \
    python3-opencv \
    python3-numpy \
    python3-serial \
    python3-venv \
    python3-pip \
    v4l-utils \
    i2c-tools \
    git \
    curl

# 2. Add user to hardware groups (camera, serial, i2c)
echo "[2/5] Configuring user permissions for Serial and Camera..."
sudo usermod -a -G dialout,video,i2c "$USER"

# 3. Create virtual environment with system site-packages
echo "[3/5] Setting up Python virtual environment (.venv)..."
if [ ! -d ".venv" ]; then
    python3 -m venv --system-site-packages .venv
fi

source .venv/bin/activate
pip install --upgrade pip

# 4. Install Python dependencies
echo "[4/5] Installing Python requirements..."
pip install -r requirements.txt

# 5. Create storage directories and fetch model weights
echo "[5/5] Preparing models and storage folders..."
mkdir -p models recordings/alerts logs

python3 training/download_weights.py || true

echo ""
echo "=================================================="
echo "  SETUP COMPLETE!                                 "
echo "=================================================="
echo "To run the robot application:"
echo "   source .venv/bin/activate"
echo "   python3 main.py"
echo ""
echo "To start the Cloud Mission Control Server:"
echo "   source .venv/bin/activate"
echo "   python3 server/app.py"
echo "=================================================="
