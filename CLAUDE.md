# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows desktop app for auto-generating HR meeting minutes. Voice/text processing runs locally; only LLM inference hits an external API.

**Stack:** Python FastAPI (port 8765) + Electron (Chromium renderer), packaged later via PyInstaller + Electron Builder.

## Commands

```bash
# Install
npm install
pip install -r minutes-app/backend/requirements.txt
python minutes-app/setup.py          # one-time: downloads ~2 GB of AI models

# Run
npm start                            # starts Electron (which spawns the FastAPI subprocess)

# Backend only (dev)
cd minutes-app/backend && uvicorn main:app --port 8765 --reload

# Package
npm run build                        # Electron Builder → dist/
```

## Architecture

```
minutes-app/
├── main.js          Electron entry: spawns backend subprocess, creates BrowserWindow
├── preload.js       contextBridge – exposes electronAPI to renderer (store, IPC events)
├── backend/
│   ├── main.py      FastAPI app: CORS + router registration + /health endpoint
│   └── routers/     One file per domain (api_key, employee, audio, transcribe, minutes)
├── frontend/
│   ├── index.html   Shell: stage header + #app-content + footer nav
│   ├── css/styles.css  All design tokens as CSS variables (--color-*, --font-*)
│   ├── js/
│   │   ├── app.js   Stage router: loads page HTML fragments into #app-content, nav logic
│   │   └── api.js   Fetch wrapper for all FastAPI endpoints (apiFetch → domain objects)
│   └── pages/       Per-stage HTML fragments (inline <script> for page-local logic)
├── models/          Git-ignored; populated by setup.py
└── setup.py         Downloads Whisper medium, pyannote 3.1, KLUE-BERT into models/
```

### Key Patterns

**Stage system (`app.js`):** 11 stages defined in `STAGES[]`. `goToStage(n)` fetches the HTML fragment and injects it into `#app-content`. Pages expose two optional hooks:
- `window.onPageLoad()` – called after injection for initialization
- `window.onNextValidate()` – called on NEXT click; return `false` to block navigation

**IPC (`preload.js` ↔ `main.js`):** Renderer accesses `window.electronAPI.store.{get,set,delete}` for persistent config (API keys stored via `electron-store`). Backend readiness is signalled via `backend:ready` / `backend:error` IPC events.

**API layer (`api.js`):** All backend calls go through `apiFetch()`. Errors are thrown as Korean-language strings and displayed directly in the UI.

**Backend subprocess:** `main.js` spawns `python backend/main.py` on app start and kills it on quit. `waitForBackend()` polls `/health` for up to 15 s before signalling an error.

## Design System

CSS variables in `frontend/css/styles.css`:

| Token | Value |
|---|---|
| `--color-bg` | `#1A1A2E` |
| `--color-bg-card` | `#0D0D1A` |
| `--color-navy` | `#002452` |
| `--color-red` | `#C51F2A` |
| `--font-title` | `'Press Start 2P'` (English titles, buttons) |
| `--font-body` | `'Noto Sans KR'` (Korean UI text) |
| `--radius-card` | `8px` |

## Important Constraints

- `models/` must never be committed (`.gitignore` enforces this).
- All user-facing error messages must be in Korean.
- The FastAPI server is strictly localhost-only (`127.0.0.1:8765`); no external exposure.
- `electron-store` (not backend) holds API keys – they never leave the device.
