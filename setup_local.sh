#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Brain-Rot Shorts Factory — Consolidated Local Setup (CachyOS)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
step()  { echo -e "${CYAN}[→]${NC} $*"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🧠🔥 Brain-Rot Shorts Factory — Local Setup (CachyOS)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Install system packages
step "System packages already installed manually."
# sudo pacman -S --needed --noconfirm ffmpeg python python-pip python-virtualenv gpu-screen-recorder


# 2. Create required directories
step "Creating workspace directories..."
mkdir -p "$HOME/Videos/RawGameplay"
mkdir -p "$HOME/Videos/RawGameplay/processed"
mkdir -p "$HOME/Videos/ProcessedShorts"
mkdir -p "$HOME/shorts_assets/audio_tracks"
mkdir -p "$HOME/.local/log"
info "Directory structure created successfully."

# 3. Setup python virtual environment
step "Setting up virtual environment..."
python -m venv "$HOME/Documents/Projects/brain-rot-factory/.venv"
source "$HOME/Documents/Projects/brain-rot-factory/.venv/bin/activate"
pip install --upgrade pip
pip install -r "$HOME/Documents/Projects/brain-rot-factory/server/requirements.txt"
deactivate
info "Virtual environment created and dependencies installed."

# 4. Install systemd user services
step "Installing systemd user services..."
mkdir -p "$HOME/.config/systemd/user"

# Copy Game Recorder service
cp "$HOME/Documents/Projects/brain-rot-factory/workstation/game-recorder.service" "$HOME/.config/systemd/user/game-recorder.service"
# Copy Watcher service
cp "$HOME/Documents/Projects/brain-rot-factory/workstation/vod-watcher.service" "$HOME/.config/systemd/user/vod-watcher.service"

systemctl --user daemon-reload
info "Services copied and daemon reloaded."

# 5. Enable Game Recorder
step "Enabling and starting hardware game recorder..."
systemctl --user enable --now game-recorder.service
info "game-recorder.service is enabled and running."

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Consolidated Local Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  📋 Next steps:"
echo "  1. 🔑 Initial YouTube Authorization Test:"
echo "     We will now prepare a mock test video to run the OAuth flow."
echo "     To do this manually, you would run:"
echo "       $HOME/Documents/Projects/brain-rot-factory/.venv/bin/python3 $HOME/Documents/Projects/brain-rot-factory/server/yt_uploader.py test.mp4"
echo ""
echo "  2. 🚀 Start the local VOD watcher daemon:"
echo "       systemctl --user enable --now vod-watcher.service"
echo ""
echo "  3. 📊 Check background activity:"
echo "       journalctl --user -u vod-watcher.service -f"
echo "       tail -f ~/.local/log/brain-rot-factory.log"
echo ""
