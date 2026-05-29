# Brain-Rot Shorts Factory

Automated **gaming highlight → vertical Short** pipeline for Linux. Record gameplay, detect hype moments with audio + vision AI, review clips in a local Control Panel, and optionally upload to YouTube Shorts.

**Repository:** [github.com/yazanj082/Brain-Rot-Factory](https://github.com/yazanj082/Brain-Rot-Factory)

---

## What it does

1. **Record** — `gpu-screen-recorder` captures your session (CachyOS / Arch).
2. **Detect** — FFmpeg audio spike analysis finds loud fight moments.
3. **Score** — [Ollama](https://ollama.com) vision rejects death cam, menus, and replays; ranks clips 1–10.
4. **Review** — Web Control Panel at `http://localhost:8069` (approve, reject, captions, upload).
5. **Upload** — Optional YouTube Data API upload on a daily schedule or manual button.

Nothing starts at login — you launch the factory from a desktop shortcut when you want to play.

---

## Requirements

| Component | Purpose |
|-----------|---------|
| **Linux** (Arch/CachyOS recommended) | Main target platform |
| **ffmpeg** | Clip cutting, vertical crop, effects |
| **gpu-screen-recorder** | Low-overhead game recording |
| **Python 3.10+** | Pipeline and dashboard |
| **Ollama** + `moondream` + `qwen2.5:7b` | Vision scoring and captions |
| **tesseract** (optional) | OCR prefilter for menus/scoreboard |

---

## Quick install

```bash
git clone https://github.com/yazanj082/Brain-Rot-Factory.git
cd Brain-Rot-Factory
chmod +x setup.sh
./setup.sh
```

`setup.sh` will:

- Install system packages (Arch: `pacman`; Debian: `apt` where available)
- Create `~/Videos/RawGameplay`, `~/Videos/ProcessedShorts`, `~/shorts_assets`, log dir
- Create a Python `.venv` and install `server/requirements.txt`
- Install **systemd user services** (disabled until you start the factory)
- Install **desktop shortcuts**: Start Factory, Stop Factory, Control Panel

### Ollama models (one time)

```bash
ollama pull moondream
ollama pull qwen2.5:7b
```

### YouTube (optional)

1. Enable **YouTube Data API v3** in [Google Cloud Console](https://console.cloud.google.com/).
2. Create OAuth **Desktop** credentials.
3. Save as `~/shorts_assets/client_secrets.json`.
4. Run a one-time auth from the project (see `server/yt_uploader.py`).

---

## Daily workflow

| Step | Action |
|------|--------|
| 1 | App menu → **Brain-Rot Start Factory** |
| 2 | Browser opens **Control Panel** → http://localhost:8069 |
| 3 | **Start Gaming Session** → pick screen/window in recorder dialog |
| 4 | Play; **Stop Recording** when done |
| 5 | **Clips** tab — approve/reject, upload best |
| 6 | **Brain-Rot Stop Factory** when finished (frees GPU RAM) |

### Recording quality (Control Panel)

**Settings** → **Recording** lets you set **FPS** (15–60) and **quality** (`ultralow` … `veryhigh` for `gpu-screen-recorder`). Click **Save settings**, then start your next session with **Start Gaming Session** — the recorder reads `~/shorts_assets/settings.json`.

### Free disk space

**Settings** → **Delete all videos & clips** removes:

- All files under `~/Videos/RawGameplay` (raw + processed VODs)
- All files under `~/Videos/ProcessedShorts` (scored, rejected, uploaded)
- All rows in the clip database

**Kept:** `~/shorts_assets/client_secrets.json`, `oauth.json`, `settings.json`, and `audio_tracks/`.

---

## Project layout

```text
Brain-Rot-Factory/
├── setup.sh                 # Main installer (run this)
├── setup_workstation.sh     # Alias → setup.sh
├── scripts/
│   ├── start-factory.sh     # Start Ollama + watcher + dashboard
│   ├── stop-factory.sh      # Stop everything
│   └── rescore-pending.sh   # Re-run AI on existing clips
├── workstation/             # systemd units + .desktop launchers
└── server/
    ├── config.py            # Paths and env overrides
    ├── vod_watcher.py       # Watches RawGameplay for new VODs
    ├── clip_scorer.py       # Ollama vision + reject policy
    ├── review_dashboard.py  # Control Panel UI + API
    ├── storage_cleanup.py   # Bulk delete for disk cleanup
    └── requirements.txt
```

---

## Configuration

Environment variables (optional — defaults work for most users):

| Variable | Default | Description |
|----------|---------|-------------|
| `BRF_WATCH_DIR` | `~/Videos/RawGameplay` | Incoming recordings |
| `BRF_OUTPUT_DIR` | `~/Videos/ProcessedShorts` | Finished shorts |
| `BRF_DB_PATH` | `~/shorts_assets/clips.db` | Clip registry |
| `BRF_DASHBOARD_PORT` | `8069` | Control Panel port |
| `BRF_MIN_HYPE_SCORE` | `6` | Min score to auto-upload |
| `BRF_VISION_MODEL` | `moondream` | Ollama vision model |
| `BRF_TEXT_MODEL` | `qwen2.5:7b` | Caption/title model |
| `record_fps` | `30` | Recording FPS (dashboard → `settings.json`) |
| `record_quality` | `high` | Recorder preset: `ultralow`, `low`, `medium`, `high`, `veryhigh` |
| `BRF_RECORD_FPS` | (from settings) | Overrides `record_fps` when set in the environment |
| `BRF_RECORD_QUALITY` | (from settings) | Overrides `record_quality` when set in the environment |

After changing services, restart the dashboard:

```bash
systemctl --user restart review-dashboard.service
```

---

## Troubleshooting

- **Control Panel buttons dead** — Hard refresh (Ctrl+Shift+R); restart `review-dashboard.service`.
- **Ollama offline** — Start Factory shortcut starts Ollama; or run `ollama serve`.
- **All clips score 8/10** — Run `./scripts/rescore-pending.sh` after upgrading.
- **Upload 401** — Delete `~/shorts_assets/oauth.json` and re-authenticate.

Logs: `~/.local/log/brain-rot-factory.log`

---

## License

MIT — see [LICENSE](LICENSE).
