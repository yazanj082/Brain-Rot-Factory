#!/usr/bin/env python3
"""
Brain-Rot Shorts Factory — Control Panel
Local web UI: start/stop recording, schedule uploads, review clips.
Open: http://localhost:8069
"""

import json
import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote

sys.path.insert(0, str(Path(__file__).parent))

import config
import clip_db
from yt_uploader import upload_to_youtube, TAGS
from metadata_generator import generate_metadata
from daily_uploader import run_daily_upload
from service_manager import (
    all_status,
    start_gaming_session,
    stop_recording,
)
from settings import load_settings, save_settings

log = logging.getLogger(__name__)
PORT = int(os.getenv("BRF_DASHBOARD_PORT", "8069"))

PANEL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brain-Rot Factory</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#0a0a0f;color:#e4e4e7;min-height:100vh}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);padding:1rem 2rem;border-bottom:1px solid rgba(255,255,255,.06);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem}
.header h1{font-size:1.3rem;font-weight:800;background:linear-gradient(135deg,#f97316,#ef4444,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hint{font-size:.8rem;color:#71717a;margin-top:.2rem}
.tabs{display:flex;gap:.5rem;padding:.75rem 2rem;background:#111;border-bottom:1px solid #27272a}
.tab{padding:.5rem 1rem;border-radius:8px;cursor:pointer;font-size:.85rem;font-weight:600;color:#71717a;background:transparent;border:none}
.tab.active{background:#27272a;color:#fff}
.tab:hover{color:#fff}
.panel{display:none;padding:2rem;max-width:1100px;margin:0 auto}
.panel.active{display:block}
.banner{background:#422006;border:1px solid #92400e;color:#fdba74;padding:.75rem 1rem;border-radius:10px;margin-bottom:1.5rem;font-size:.85rem}
.status-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:1rem;margin-bottom:1.5rem}
.card{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:1rem}
.card-label{font-size:.7rem;color:#71717a;text-transform:uppercase;letter-spacing:.05em}
.card-value{font-size:1rem;font-weight:600;margin-top:.35rem;display:flex;align-items:center;gap:.4rem}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.on{background:#22c55e}.dot.off{background:#ef4444}
.actions{display:flex;flex-wrap:wrap;gap:.75rem;margin-bottom:1.5rem}
.btn{padding:.7rem 1.25rem;border:none;border-radius:10px;font-family:inherit;font-size:.85rem;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;gap:.4rem}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-primary{background:linear-gradient(135deg,#f97316,#ea580c);color:#fff}
.btn-primary:hover:not(:disabled){filter:brightness(1.1)}
.btn-secondary{background:#27272a;color:#e4e4e7}
.btn-secondary:hover:not(:disabled){background:#3f3f46}
.btn-success{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff}
.btn-danger{background:#7f1d1d;color:#fca5a5}
.schedule{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:1.25rem;margin-bottom:1.5rem}
.schedule h3{font-size:.95rem;margin-bottom:1rem}
.schedule-row{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;margin-bottom:.75rem}
.schedule-row label{font-size:.8rem;color:#a1a1aa}
.schedule-row input[type=number]{width:70px;padding:.4rem;border-radius:6px;border:1px solid #3f3f46;background:#0a0a0f;color:#fff}
.toggle{display:flex;align-items:center;gap:.5rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1.25rem}
.clip-card{background:#18181b;border:1px solid #27272a;border-radius:14px;overflow:hidden}
.clip-card.pick{border-color:#f97316;box-shadow:0 0 0 1px #f97316}
.clip-card video{width:100%;aspect-ratio:9/16;object-fit:contain;background:#000;max-height:360px;display:block;pointer-events:auto}
.clip-body{padding:1rem}
.badge{display:inline-block;padding:.2rem .5rem;border-radius:6px;font-size:.7rem;font-weight:600;margin-right:.3rem}
.badge-scored{background:#14532d;color:#86efac}
.badge-rejected{background:#450a0a;color:#fca5a5}
.badge-pending{background:#422006;color:#fdba74}
.rank-badge{display:inline-block;background:linear-gradient(135deg,#f97316,#ea580c);color:#fff;font-size:1rem;font-weight:800;padding:.25rem .55rem;border-radius:8px;margin-right:.5rem;min-width:2rem;text-align:center}
.pick-label{display:block;color:#f97316;font-size:.75rem;font-weight:700;margin-bottom:.35rem}
.hype{font-size:1.1rem;font-weight:700;color:#f97316}
.caption{font-size:.8rem;color:#d4d4d8;margin:.4rem 0;line-height:1.45;white-space:pre-wrap}
.caption-pending{font-size:.8rem;color:#71717a;font-style:italic}
.warn-replay{font-size:.7rem;color:#fbbf24;margin-top:.25rem}
.clip-actions{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.75rem}
.clip-actions .btn{flex:1;font-size:.75rem;padding:.5rem}
.empty{text-align:center;padding:3rem;color:#52525b}
.history-item{background:#18181b;border:1px solid #27272a;border-radius:10px;padding:1rem;margin-bottom:.75rem}
.history-item a{color:#22c55e}
.toast{position:fixed;bottom:1.5rem;right:1.5rem;background:#27272a;padding:1rem 1.25rem;border-radius:10px;border:1px solid #3f3f46;z-index:999;display:none;max-width:320px;font-size:.85rem}
.toast.show{display:block}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>Brain-Rot Factory</h1>
    <div class="hint">Start session, play, stop recording. Best clip uploads on your schedule.</div>
  </div>
</div>
<div class="tabs">
  <button class="tab active" data-tab="home">Home</button>
  <button class="tab" data-tab="clips">Clips</button>
  <button class="tab" data-tab="history">History</button>
  <button class="tab" data-tab="settings">Settings</button>
</div>

<div id="banner" class="banner" style="display:none"></div>

<div id="home" class="panel active">
  <div class="actions">
    <button class="btn btn-primary" id="btnStart">Start Gaming Session</button>
    <button class="btn btn-secondary" id="btnStop">Stop Recording</button>
    <button class="btn btn-success" id="btnUploadNow">Upload Best Clip Now</button>
  </div>
  <div class="status-grid" id="statusGrid"></div>
  <div class="schedule">
    <h3>Daily auto-upload schedule</h3>
    <div class="schedule-row">
      <label>Time</label>
      <input type="number" id="uploadHour" min="0" max="23" value="22"> :
      <input type="number" id="uploadMinute" min="0" max="59" value="0">
      <label class="toggle"><input type="checkbox" id="autoUpload" checked> Auto-upload daily</label>
      <button class="btn btn-secondary" id="btnSaveSchedule">Save schedule</button>
    </div>
    <div id="countdown" style="font-size:.8rem;color:#71717a"></div>
  </div>
</div>

<div id="clips" class="panel">
  <div class="grid" id="clipsGrid"></div>
</div>

<div id="history" class="panel">
  <div id="historyList"></div>
  <p style="margin-top:1rem;font-size:.8rem;color:#52525b">Log file: <code id="logPath"></code></p>
</div>

<div id="settings" class="panel">
  <div class="schedule">
    <h3>Quality threshold</h3>
    <div class="schedule-row">
      <label>Min hype score (1-10)</label>
      <input type="number" id="minHype" min="1" max="10" step="0.5" value="6">
      <label>Game name</label>
      <input type="text" id="gameName" value="Overwatch" style="width:140px;padding:.4rem;border-radius:6px;border:1px solid #3f3f46;background:#0a0a0f;color:#fff">
      <button class="btn btn-secondary" id="btnSaveSettings">Save settings</button>
    </div>
    <div class="schedule" style="margin-top:1.5rem;border-color:#7f1d1d">
      <h3 style="color:#fca5a5">Free disk space</h3>
      <p style="font-size:.8rem;color:#a1a1aa;margin-bottom:.75rem">
        Permanently deletes all raw recordings, processed VODs, and every clip (scored, rejected, uploaded).
        Keeps YouTube OAuth, settings, and your music pool in <code>~/shorts_assets</code>.
      </p>
      <button type="button" class="btn btn-danger" id="btnCleanupAll">Delete all videos &amp; clips</button>
    </div>
    <details style="margin-top:1rem;font-size:.8rem;color:#71717a">
      <summary style="cursor:pointer;color:#a1a1aa">Advanced (Ollama models)</summary>
      <div class="schedule-row" style="margin-top:.75rem">
        <label>Vision model</label>
        <input type="text" id="visionModel" style="width:200px;padding:.4rem;border-radius:6px;border:1px solid #3f3f46;background:#0a0a0f;color:#fff">
        <label>Text model</label>
        <input type="text" id="textModel" style="width:200px;padding:.4rem;border-radius:6px;border:1px solid #3f3f46;background:#0a0a0f;color:#fff">
      </div>
    </details>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const $ = (s) => document.querySelector(s);
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 4000);
}
let activeTab = 'home';
let lastClipsFingerprint = '';

document.querySelectorAll('.tab').forEach(tab => {
  tab.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    $(`#${tab.dataset.tab}`).classList.add('active');
    activeTab = tab.dataset.tab;
    if (activeTab === 'clips' || activeTab === 'history') {
      refresh({ forceClips: activeTab === 'clips' });
    }
  };
});

async function api(path, method='GET', body=null) {
  try {
    const opts = { method, headers: {} };
    if (body) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    let data;
    try {
      data = await r.json();
    } catch (parseErr) {
      return { ok: false, success: false, error: 'Server returned invalid JSON (HTTP ' + r.status + ')' };
    }
    if (!r.ok) {
      return {
        ...data,
        ok: false,
        success: false,
        error: data.error || ('Request failed (HTTP ' + r.status + ')'),
      };
    }
    if (data.ok === undefined && data.success === undefined) {
      data.ok = true;
    }
    return data;
  } catch (err) {
    return { ok: false, success: false, error: err.message || String(err) };
  }
}

function fmtCountdown(sec) {
  if (sec <= 0) return 'soon';
  const h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

function renderStatus(d) {
  const g = $('#statusGrid');
  const rec = d.recorder?.active;
  const watch = d.watcher?.active;
  const oll = d.ollama?.active;
  const sch = d.schedule || {};
  g.innerHTML = `
    <div class="card"><div class="card-label">Recording</div><div class="card-value"><span class="dot ${rec?'on':'off'}"></span>${rec?'ON':'OFF'}</div></div>
    <div class="card"><div class="card-label">Clip processor</div><div class="card-value"><span class="dot ${watch?'on':'off'}"></span>${watch?'ON':'OFF'}</div></div>
    <div class="card"><div class="card-label">Ollama AI</div><div class="card-value"><span class="dot ${oll?'on':'off'}"></span>${oll?'Ready':'Offline'}</div></div>
    <div class="card"><div class="card-label">Auto-upload</div><div class="card-value">${sch.auto_upload_enabled ? `ON at ${String(sch.upload_hour).padStart(2,'0')}:${String(sch.upload_minute).padStart(2,'0')}` : 'OFF'}</div></div>
    <div class="card"><div class="card-label">Clips ready</div><div class="card-value">${d.queue?.scored||0} scored</div></div>
    <div class="card"><div class="card-label">Next upload</div><div class="card-value">${sch.auto_upload_enabled ? fmtCountdown(sch.seconds_until||0) : 'manual only'}</div></div>
  `;
  $('#countdown').textContent = sch.auto_upload_enabled
    ? `Next auto-upload in ${fmtCountdown(sch.seconds_until||0)}`
    : 'Auto-upload disabled — use Upload Best Clip Now';
  const banner = $('#banner');
  if (!oll) {
    banner.style.display = 'block';
    banner.textContent = 'Ollama is offline. Clips will queue until AI is back. Start Ollama on your system.';
  } else banner.style.display = 'none';
  if (d.tonights_pick) {
    const p = d.tonights_pick;
    banner.style.display = 'block';
    banner.textContent = `Tonight's pick: hype ${p.hype_score}/10 — ${p.summary || p.file_path}`;
  }
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function escapeAttr(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}

function escapeTemplate(s) {
  s = escapeHtml(s);
  return s.split('\\\\').join('\\\\\\\\').split('`').join('\\\\`').split('${').join('\\\\${');
}

function renderClipCard(c) {
  const st = c.status || 'unknown';
  const fn = c.filename || '';
  const badgeCls = st === 'scored' ? 'badge-scored'
    : st === 'rejected' ? 'badge-rejected' : 'badge-pending';
  const statusLabel = st === 'pending_score' ? 'scoring...' : st;
  const rank = c.rank ? `<span class="rank-badge">#${c.rank}</span>` : '';
  const hype = c.hype_score != null
    ? `<span class="hype">${Number(c.hype_score).toFixed(1)}/10</span>` : '';
  const pick = c.is_pick ? 'pick' : '';
  const pickLabel = c.is_pick ? '<span class="pick-label">Tonight\u2019s pick</span>' : '';
  const df = escapeAttr(fn);
  let caption = '';
  if (st === 'scored') {
    if (c.description) {
      caption = `<div class="caption"><strong>Caption</strong><br>${escapeTemplate(c.description)}</div>`;
    } else if (c.summary) {
      caption = `<div class="caption-pending">Generating caption…<br><span style="color:#52525b">${escapeTemplate(c.summary)}</span></div>`;
    } else {
      caption = '<div class="caption-pending">Generating caption…</div>';
    }
  }
  const whyRejected = st === 'rejected'
    ? `<div style="color:#f87171;font-size:.75rem;margin-top:.3rem"><strong>Why rejected:</strong> ${escapeTemplate(c.reject_reason || 'Unknown (re-score this clip)')}</div>` : '';
  const approveBtn = (st === 'rejected' || st === 'pending_score')
    ? `<button type="button" class="btn btn-success" data-action="approve" data-filename="${df}">Approve</button>` : '';
  const rejectBtn = st === 'scored'
    ? `<button type="button" class="btn btn-secondary" data-action="reject" data-filename="${df}">Reject</button>` : '';
  const regenBtn = st === 'scored'
    ? `<button type="button" class="btn btn-secondary" data-action="regen-caption" data-filename="${df}">Refresh caption</button>` : '';
  const uploadBtn = st === 'scored'
    ? `<button type="button" class="btn btn-primary" data-action="upload" data-filename="${df}">Upload</button>` : '';
  return `<div class="clip-card ${pick}">
    <video controls preload="metadata"><source src="/video/${encodeURIComponent(fn)}" type="video/mp4"></video>
    <div class="clip-body">
      ${pickLabel}
      <div style="display:flex;align-items:center;flex-wrap:wrap;gap:.35rem;margin-bottom:.35rem">
        ${rank}<span class="badge ${badgeCls}">${statusLabel}</span>${hype}
      </div>
      ${c.title ? `<div style="font-size:.85rem;font-weight:600;margin-bottom:.25rem">${escapeTemplate(c.title)}</div>` : ''}
      ${caption}
      ${c.spike_energy != null ? `<div style="font-size:.7rem;color:#52525b">Audio peak: ${Number(c.spike_energy).toFixed(2)}x session avg</div>` : ''}
      <div style="font-size:.7rem;color:#52525b">${escapeTemplate(fn)}</div>
      ${whyRejected}
      <div class="clip-actions">
        ${approveBtn}${rejectBtn}${regenBtn}${uploadBtn}
        <button type="button" class="btn btn-danger" data-action="delete" data-filename="${df}">Delete</button>
      </div>
    </div>
  </div>`;
}

function renderClips(clips) {
  const grid = $('#clipsGrid');
  if (!clips.length) {
    grid.innerHTML = '<div class="empty">No clips waiting. Record a session first.</div>';
    return;
  }
  const parts = [];
  for (const c of clips) {
    try {
      parts.push(renderClipCard(c));
    } catch (err) {
      console.error('renderClipCard failed', c.filename, err);
      parts.push(`<div class="clip-card"><div class="clip-body">Could not render ${escapeHtml(c.filename || 'clip')}</div></div>`);
    }
  }
  grid.innerHTML = parts.join('');
}

function renderHistory(uploads, rejected) {
  let html = '';
  if (!uploads.length) html += '<div class="empty">No uploads yet.</div>';
  uploads.forEach(u => {
    const link = u.youtube_id ? `<a href="https://youtube.com/shorts/${u.youtube_id}" target="_blank">View on YouTube</a>` : '';
    html += `<div class="history-item"><strong>${u.title||'Untitled'}</strong> — hype ${u.hype_score||'?'}/10<br>
      <span style="font-size:.8rem;color:#71717a">${u.uploaded_at||''}</span><br>${link}</div>`;
  });
  html += `<p style="margin-top:1rem;color:#71717a;font-size:.85rem">Rejected clips: ${rejected}</p>`;
  $('#historyList').innerHTML = html;
}

function clipsFingerprint(clips) {
  return clips.map(c =>
    `${c.filename}|${c.status}|${c.hype_score}|${c.rank}|${c.reject_reason||''}|${c.description||''}`
  ).sort().join('|');
}

function isClipVideoPlaying() {
  return !!document.querySelector('#clips video:not([paused])');
}

function isSettingsFocused() {
  const el = document.activeElement;
  return activeTab === 'settings' && el && el.closest && el.closest('#settings');
}

async function refresh(opts = {}) {
  const forceClips = !!opts.forceClips;
  try {
    const d = await api('/api/status');
    renderStatus(d);

    const clips = d.clips || [];
    const fp = clipsFingerprint(clips);
    const skipClips = !forceClips && activeTab === 'clips'
      && (isClipVideoPlaying() || fp === lastClipsFingerprint);
    if (!skipClips) {
      renderClips(clips);
      lastClipsFingerprint = fp;
    }

    if (activeTab === 'history') {
      renderHistory(d.uploads || [], d.queue?.rejected || 0);
    }

    if (!isSettingsFocused()) {
      const s = d.settings || {};
      $('#uploadHour').value = s.upload_hour ?? 22;
      $('#uploadMinute').value = s.upload_minute ?? 0;
      $('#autoUpload').checked = s.auto_upload_enabled !== false;
      $('#minHype').value = s.min_hype_score ?? 6;
      $('#gameName').value = s.game_name || 'Overwatch';
      $('#visionModel').value = s.vision_model || '';
      $('#textModel').value = s.textModel || s.text_model || '';
    }
    $('#logPath').textContent = d.log_path || '';
  } catch(e) { console.error(e); }
}

$('#btnStart').onclick = async () => {
  const r = await api('/api/session/start', 'POST');
  toast(r.ok
    ? 'Recording starting — pick your game window or screen in the dialog!'
    : 'Failed to start: ' + (r.error||''));
  refresh({ forceClips: true });
};
$('#btnStop').onclick = async () => {
  const r = await api('/api/session/stop', 'POST');
  toast(r.ok ? 'Recording stopped. Processing your VOD...' : 'Failed: ' + (r.error||''));
  refresh({ forceClips: true });
};
$('#btnUploadNow').onclick = async () => {
  if (!confirm('Upload the best scored clip to YouTube now?')) return;
  toast('Uploading...');
  const r = await api('/api/upload-now', 'POST');
  if (r.success) toast('Uploaded! ' + (r.url||''));
  else toast('Failed: ' + (r.error||'unknown'));
  refresh({ forceClips: true });
};
$('#btnSaveSchedule').onclick = async () => {
  await api('/api/settings', 'POST', {
    upload_hour: +$('#uploadHour').value,
    upload_minute: +$('#uploadMinute').value,
    auto_upload_enabled: $('#autoUpload').checked,
  });
  toast('Schedule saved');
  refresh({ forceClips: true });
};
$('#btnSaveSettings').onclick = async () => {
  await api('/api/settings', 'POST', {
    min_hype_score: +$('#minHype').value,
    game_name: $('#gameName').value,
    vision_model: $('#visionModel').value,
    text_model: $('#textModel').value,
  });
  toast('Settings saved');
  refresh({ forceClips: true });
};
$('#btnCleanupAll').onclick = async () => {
  if (!confirm('Delete ALL raw VODs and ALL clips from this PC? This cannot be undone.')) return;
  if (prompt('Type DELETE ALL to confirm:') !== 'DELETE ALL') {
    toast('Cleanup cancelled');
    return;
  }
  toast('Deleting files…');
  const r = await api('/api/cleanup-all', 'POST', { confirm: 'DELETE ALL' });
  if (r.ok) {
    toast('Freed ' + (r.mb_freed || 0) + ' MB (' + (r.files_deleted || 0) + ' files). DB cleared.');
    refresh({ forceClips: true });
  } else {
    toast(r.error || 'Cleanup failed');
  }
};

async function handleClipAction(action, filename) {
  if (!filename) {
    toast('Missing clip filename');
    return;
  }
  try {
    if (action === 'approve') {
      const r = await api('/api/clip/approve', 'POST', { filename });
      toast(r.ok ? 'Clip approved' : (r.error || 'Approve failed'));
    } else if (action === 'reject') {
      const reason = prompt('Reject reason (optional):') || '';
      const r = await api('/api/clip/reject', 'POST', { filename, reason });
      toast(r.ok ? 'Clip rejected' : (r.error || 'Reject failed'));
    } else if (action === 'delete') {
      if (!confirm('Delete this clip permanently?')) return;
      const r = await api('/api/delete', 'POST', { filename });
      toast(r.success ? 'Clip deleted' : (r.error || 'Delete failed'));
    } else if (action === 'upload') {
      if (!confirm('Upload this clip to YouTube?')) return;
      toast('Uploading…');
      const r = await api('/api/upload', 'POST', { filename });
      toast(r.success ? 'Uploaded!' : (r.error || 'Upload failed'));
    } else if (action === 'regen-caption') {
      toast('Generating caption…');
      const r = await api('/api/clip/regenerate-metadata', 'POST', { filename });
      toast(r.ok ? 'Caption updated' : (r.error || 'Caption failed'));
    }
    refresh({ forceClips: true });
  } catch (err) {
    console.error('handleClipAction', action, err);
    toast('Error: ' + (err.message || err));
  }
}

$('#clipsGrid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  e.preventDefault();
  const action = btn.dataset.action;
  const filename = btn.dataset.filename;
  handleClipAction(action, filename);
});

refresh({ forceClips: true });
setInterval(() => refresh(), 15000);
</script>
</body>
</html>"""


class DashboardHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(format, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", ""):
            self._serve_panel()
        elif parsed.path == "/api/status":
            self._api_status()
        elif parsed.path == "/api/settings":
            self._api_get_settings()
        elif parsed.path.startswith("/video/"):
            self._serve_video(parsed.path[7:])
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_json()
        routes = {
            "/api/upload": self._handle_upload,
            "/api/delete": self._handle_delete,
            "/api/settings": self._handle_settings,
            "/api/session/start": self._handle_session_start,
            "/api/session/stop": self._handle_session_stop,
            "/api/upload-now": self._handle_upload_now,
            "/api/clip/reject": self._handle_clip_reject,
            "/api/clip/approve": self._handle_clip_approve,
            "/api/clip/regenerate-metadata": self._handle_regenerate_metadata,
            "/api/cleanup-all": self._handle_cleanup_all,
        }
        handler = routes.get(parsed.path)
        if handler:
            handler(body)
        else:
            self.send_error(404)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            return {}

    def _json(self, obj: dict, status: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_panel(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(PANEL_HTML.encode())

    def _serve_video(self, filename: str):
        """Serve MP4 with Range support so the browser timeline can seek."""
        import re

        filename = unquote(filename)
        if ".." in filename or "/" in filename or "\\" in filename:
            self.send_error(403)
            return

        video_path = config.OUTPUT_DIR / filename
        if not video_path.exists():
            rejected = config.REJECTED_DIR / filename
            if rejected.exists():
                video_path = rejected
            else:
                self.send_error(404)
                return

        size = video_path.stat().st_size
        range_header = self.headers.get("Range")

        if range_header:
            match = re.match(r"bytes=(\d+)-(\d*)", range_header.strip())
            if match:
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
                if start >= size:
                    self.send_error(416)
                    return
                end = min(end, size - 1)
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.end_headers()
                with open(video_path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
                return

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(video_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _clip_ui_entry(self, f: Path, pick_id: int | None) -> dict:
        db_clip = clip_db.get_clip_by_path(f)
        return {
            "filename": f.name,
            "file_path": str(f),
            "status": db_clip.get("status", "unknown") if db_clip else "unknown",
            "hype_score": db_clip.get("hype_score") if db_clip else None,
            "spike_energy": db_clip.get("spike_energy") if db_clip else None,
            "summary": db_clip.get("summary") if db_clip else None,
            "title": db_clip.get("title") if db_clip else None,
            "description": db_clip.get("description") if db_clip else None,
            "has_replay": bool(db_clip.get("has_replay")) if db_clip else False,
            "reject_reason": db_clip.get("reject_reason") if db_clip else None,
            "is_pick": db_clip and db_clip.get("id") == pick_id,
            "created_at": db_clip.get("created_at", "") if db_clip else "",
            "clip_id": db_clip.get("id") if db_clip else None,
        }

    def _list_clips_for_ui(self) -> list:
        pick = clip_db.get_tonights_pick()
        pick_id = pick["id"] if pick else None

        by_filename: dict[str, dict] = {}

        for folder in (config.OUTPUT_DIR, config.REJECTED_DIR):
            if not folder.exists():
                continue
            for f in folder.glob("*.mp4"):
                by_filename[f.name] = self._clip_ui_entry(f, pick_id)

        clips = list(by_filename.values())

        def sort_key(c):
            hype = c.get("hype_score")
            if hype is None:
                return (1, 0, c.get("created_at", ""))
            return (0, -float(hype), c.get("created_at", ""))

        clips.sort(key=sort_key)

        rank = 0
        for c in clips:
            if c.get("status") == "scored" and c.get("hype_score") is not None:
                rank += 1
                c["rank"] = rank
            else:
                c["rank"] = None

        return clips

    def _api_status(self):
        try:
            status = all_status()
        except Exception as exc:
            status = {"error": str(exc)}
        status["clips"] = self._list_clips_for_ui()
        status["uploads"] = clip_db.list_uploaded(10)
        status["settings"] = load_settings()
        status["log_path"] = str(config.LOG_FILE)
        self._json(status)

    def _api_get_settings(self):
        self._json(load_settings())

    def _handle_settings(self, data: dict):
        allowed = {
            "upload_hour", "upload_minute", "auto_upload_enabled",
            "min_hype_score", "game_name", "vision_model", "text_model",
        }
        updates = {k: v for k, v in data.items() if k in allowed}
        save_settings(updates)
        self._json({"ok": True, "settings": load_settings()})

    def _handle_session_start(self, data: dict):
        try:
            results = start_gaming_session()
            ok = results.get("recorder", {}).get("ok", False)
            self._json({"ok": ok, "results": results})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})

    def _handle_session_stop(self, data: dict):
        try:
            results = stop_recording()
            ok = results.get("recorder", {}).get("ok", True)
            self._json({"ok": ok, "results": results})
        except Exception as exc:
            self._json({"ok": False, "error": str(exc)})

    def _handle_upload_now(self, data: dict):
        result_holder = {}

        def run():
            result_holder["result"] = run_daily_upload(force=True)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=600)
        result = result_holder.get("result", {"success": False, "error": "Timeout"})
        self._json(result)

    def _handle_clip_reject(self, data: dict):
        from clip_actions import manual_reject

        filename = data.get("filename", "")
        result = manual_reject(filename, data.get("reason"))
        self._json(result)

    def _handle_clip_approve(self, data: dict):
        from clip_actions import manual_approve

        filename = data.get("filename", "")
        result = manual_approve(filename)
        self._json(result)

    def _handle_regenerate_metadata(self, data: dict):
        from clip_actions import resolve_clip_path
        from clip_scorer import generate_metadata_for_clip

        filename = data.get("filename", "")
        path = resolve_clip_path(filename)
        if not path:
            self._json({"ok": False, "error": "File not found"})
            return
        clip = clip_db.get_clip_by_path(path)
        if not clip:
            self._json({"ok": False, "error": "Clip not in database"})
            return
        ok = generate_metadata_for_clip(clip["id"])
        self._json({"ok": ok})

    def _handle_upload(self, data: dict):
        from clip_actions import resolve_clip_path

        filename = data.get("filename", "")
        video_path = resolve_clip_path(filename)
        if not video_path or not video_path.exists():
            self._json({"success": False, "error": "File not found"})
            return

        db_clip = clip_db.get_clip_by_path(video_path)
        if db_clip:
            clip_id = db_clip["id"]
            if db_clip.get("title") and db_clip.get("description"):
                title = db_clip["title"]
                desc = db_clip["description"]
                tags = db_clip.get("tags") or TAGS
                if isinstance(tags, str):
                    import json as _json
                    try:
                        tags = _json.loads(tags)
                    except _json.JSONDecodeError:
                        tags = TAGS
            else:
                meta = generate_metadata(
                    db_clip.get("summary") or "",
                    float(db_clip.get("hype_score") or 0),
                )
                title, desc, tags = meta["title"], meta["description"], meta["tags"]
        else:
            clip_id = None
            from brain_rot_factory import generate_title
            title, desc, tags = generate_title(), None, TAGS

        video_id = upload_to_youtube(
            video_path, title=title, description=desc, tags=tags, clip_id=clip_id
        )
        if video_id:
            config.UPLOADED_DIR.mkdir(exist_ok=True)
            video_path.rename(config.UPLOADED_DIR / filename)
            self._json({"success": True, "video_id": video_id})
        else:
            self._json({"success": False, "error": "Upload failed"})

    def _handle_delete(self, data: dict):
        from clip_actions import resolve_clip_path

        filename = data.get("filename", "")
        video_path = resolve_clip_path(filename)
        if video_path and video_path.exists():
            db_clip = clip_db.get_clip_by_path(video_path)
            video_path.unlink()
            if db_clip:
                clip_db.delete_clip_record(db_clip["id"])
            self._json({"success": True})
        else:
            self._json({"success": False, "error": "Not found"})

    def _handle_cleanup_all(self, data: dict):
        if data.get("confirm") != "DELETE ALL":
            self._json({"ok": False, "error": 'Confirmation required: send {"confirm":"DELETE ALL"}'})
            return
        try:
            from storage_cleanup import cleanup_all_local_media

            result = cleanup_all_local_media()
            log.info(
                "Cleanup-all: %s files, %.1f MB",
                result.get("files_deleted"),
                result.get("mb_freed"),
            )
            self._json(result)
        except Exception as exc:
            log.exception("cleanup-all failed")
            self._json({"ok": False, "error": str(exc)})


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    log.info("Control Panel at http://localhost:%d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
