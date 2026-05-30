#!/usr/bin/env bash
# Brain-Rot Shorts Factory — full local setup (deps, dirs, venv, services, shortcuts)
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
step()  { echo -e "${CYAN}[→]${NC} $*"; }
die()   { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_SYSTEMD="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
VENV="$SCRIPT_DIR/.venv"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Brain-Rot Shorts Factory — Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── System packages ─────────────────────────────────────────────
step "Installing system dependencies..."

install_arch() {
  local pkgs=(ffmpeg python python-pip gpu-screen-recorder tesseract)
  if ! command -v ollama &>/dev/null; then
    pkgs+=(ollama)
  fi
  if command -v pacman &>/dev/null; then
    sudo pacman -S --needed --noconfirm "${pkgs[@]}" 2>/dev/null || {
      warn "Some Arch packages missing — install manually: ${pkgs[*]}"
      sudo pacman -S --needed --noconfirm ffmpeg python gpu-screen-recorder || true
    }
  fi
}

install_debian() {
  if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y ffmpeg python3 python3-venv python3-pip tesseract-ocr || true
    warn "gpu-screen-recorder is not in apt — install from source or use another recorder on Debian/Ubuntu."
  fi
}

if command -v pacman &>/dev/null; then
  install_arch
elif command -v apt-get &>/dev/null; then
  install_debian
else
  warn "Unknown distro — ensure ffmpeg, python3, and gpu-screen-recorder are installed."
fi

for cmd in ffmpeg python3; do
  command -v "$cmd" &>/dev/null || die "Missing required command: $cmd"
done
info "Core tools: ffmpeg, python3"

if ! command -v gpu-screen-recorder &>/dev/null; then
  warn "gpu-screen-recorder not found — recording will not work until you install it."
fi
if ! command -v ollama &>/dev/null; then
  warn "ollama not found — install from https://ollama.com then: ollama pull moondream && ollama pull qwen2.5:7b"
else
  info "ollama available"
fi
if ! command -v tesseract &>/dev/null; then
  warn "tesseract not found (optional OCR prefilter)"
fi

# ── Directories (match server/config.py defaults) ───────────────
step "Creating data directories..."
mkdir -p \
  "$HOME/Videos/RawGameplay/processed" \
  "$HOME/Videos/ProcessedShorts/rejected" \
  "$HOME/Videos/ProcessedShorts/uploaded" \
  "$HOME/shorts_assets/audio_tracks" \
  "$HOME/.local/log"
info "Videos and assets folders ready"

# ── Python venv ─────────────────────────────────────────────────
step "Python virtual environment..."
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$SCRIPT_DIR/server/requirements.txt"
info "Python dependencies installed in .venv"

# ── systemd user units ──────────────────────────────────────────
step "Installing systemd user services..."
mkdir -p "$USER_SYSTEMD"
for svc in game-recorder vod-watcher review-dashboard; do
  src="$SCRIPT_DIR/workstation/${svc}.service"
  if [[ -f "$src" ]]; then
    dest="$USER_SYSTEMD/${svc}.service"
    sed -e "s|/home/yazan|$HOME|g" \
        -e "s|/home/yazan/Documents/Projects/brain-rot-factory|$SCRIPT_DIR|g" \
        "$src" > "$dest"
    info "Installed ${svc}.service"
  fi
done

if command -v systemctl &>/dev/null && systemctl --user show-environment &>/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user disable --now vod-watcher.service review-dashboard.service game-recorder.service 2>/dev/null || true
  info "Services disabled at login (start via desktop shortcut)"
else
  warn "systemd user session not available — skip service enable/disable"
fi

# ── Desktop shortcuts ───────────────────────────────────────────
step "Installing desktop shortcuts..."
mkdir -p "$DESKTOP_DIR"
for desk in brain-rot-factory brain-rot-start brain-rot-stop; do
  src="$SCRIPT_DIR/workstation/${desk}.desktop"
  dest="$DESKTOP_DIR/${desk}.desktop"
  if [[ -f "$src" ]]; then
    sed -e "s|/home/yazan|$HOME|g" \
        -e "s|/home/yazan/Documents/Projects/brain-rot-factory|$SCRIPT_DIR|g" \
        "$src" > "$dest"
    chmod +x "$dest" 2>/dev/null || true
  fi
done
chmod +x \
  "$SCRIPT_DIR/setup.sh" \
  "$SCRIPT_DIR/scripts/start-factory.sh" \
  "$SCRIPT_DIR/scripts/stop-factory.sh" \
  "$SCRIPT_DIR/scripts/rescore-pending.sh" \
  2>/dev/null || true
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
info "App menu: Brain-Rot Start / Stop / Control Panel"

# ── Initialize SQLite (creates DB on first import) ──────────────
step "Initializing clip database..."
"$VENV/bin/python3" -c "import sys; sys.path.insert(0, '$SCRIPT_DIR/server'); import clip_db" 2>/dev/null || warn "DB init skipped (run factory once to create)"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "Setup complete!"
echo ""
echo "  Repo path: $SCRIPT_DIR"
echo "  1. Menu → Brain-Rot Start Factory (watcher + dashboard only)"
echo "  2. Open http://localhost:8069"
echo "  3. Start Gaming Session → record → Stop Recording (Ollama starts here)"
echo "  4. Review clips; Stop Factory when done"
echo ""
echo "  One-time AI models (stored in ~/.ollama, survive reboot):"
echo "    ollama pull moondream"
echo "    ollama pull qwen2.5:7b"
echo ""
echo "  YouTube (optional): ~/shorts_assets/client_secrets.json"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
