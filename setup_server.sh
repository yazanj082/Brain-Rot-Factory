#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Brain-Rot Shorts Factory — Server Setup (Orange Pi / Debian / Armbian)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
step()  { echo -e "${CYAN}[→]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🧠🔥 Brain-Rot Shorts Factory — Server Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. System dependencies
step "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg python3 python3-pip python3-venv syncthing
info "System packages installed."

# 2. Create directory structure
step "Creating directories..."
mkdir -p "$HOME/Videos/RawGameplay"
mkdir -p "$HOME/Videos/RawGameplay/processed"
mkdir -p "$HOME/Videos/ProcessedShorts"
mkdir -p "$HOME/shorts_assets/audio_tracks"
mkdir -p "$HOME/.local/log"
info "Directories created:"
echo "      ~/Videos/RawGameplay/          (Syncthing incoming VODs)"
echo "      ~/Videos/RawGameplay/processed (Archived VODs)"
echo "      ~/Videos/ProcessedShorts/      (Generated shorts)"
echo "      ~/shorts_assets/audio_tracks/  (Background music pool)"

# 3. Python virtual environment + dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
step "Setting up Python virtual environment..."
python3 -m venv "$SCRIPT_DIR/server/.venv"
source "$SCRIPT_DIR/server/.venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/server/requirements.txt" -q
deactivate
info "Python dependencies installed in server/.venv"

# 4. Install systemd service
step "Installing vod-watcher systemd service..."
SERVICE_SRC="$SCRIPT_DIR/server/vod-watcher.service"

# Update the ExecStart to use the venv Python
VENV_PYTHON="$SCRIPT_DIR/server/.venv/bin/python3"
sudo cp "$SERVICE_SRC" /etc/systemd/system/vod-watcher.service

# Patch the service to use the virtualenv python
sudo sed -i "s|ExecStart=/usr/bin/python3|ExecStart=$VENV_PYTHON|" /etc/systemd/system/vod-watcher.service
sudo systemctl daemon-reload
info "Service installed to /etc/systemd/system/vod-watcher.service"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Server setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  📋 Remaining manual steps:"
echo ""
echo "  1. 🔗 SYNCTHING — Connect your workstation's ~/Videos/RawGameplay"
echo "     to this server. Open http://localhost:8384 on both machines."
echo ""
echo "  2. 🔑 YOUTUBE OAUTH — Complete one-time authorisation:"
echo "     a) Place your client_secrets.json in ~/shorts_assets/"
echo "     b) Run:  cd $SCRIPT_DIR/server && .venv/bin/python3 yt_uploader.py test.mp4"
echo "     c) Follow the browser link to authorise your Google account."
echo ""
echo "  3. 🎵 BACKGROUND MUSIC — Add .mp3/.ogg/.wav tracks to:"
echo "     ~/shorts_assets/audio_tracks/"
echo ""
echo "  4. 🚀 START THE DAEMON:"
echo "     sudo systemctl enable --now vod-watcher.service"
echo "     sudo systemctl status vod-watcher.service"
echo ""
echo "  5. 📊 VIEW LOGS:"
echo "     tail -f ~/.local/log/brain-rot-factory.log"
echo ""
