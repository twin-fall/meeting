# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows desktop app for auto-generating HR meeting minutes. Voice/text processing runs locally; only LLM inference hits an external API.

**Stack:** Python FastAPI (port 8765) + Electron (Chromium renderer), packaged later via PyInstaller + Electron Builder.

## Commands

```bash
# Install
npm install                                          # from minutes-app/
pip install -r minutes-app/backend/requirements.txt
python minutes-app/setup.py                          # one-time: downloads ~2 GB of AI models

# Run
npm start                                            # starts Electron (which spawns the FastAPI subprocess)

# Backend only (dev)
cd minutes-app/backend && uvicorn main:app --port 8765 --reload

# Package
npm run build                                        # Electron Builder → dist/
```

## Architecture

```
minutes-app/
├── main.js          Electron entry: spawns backend subprocess, creates BrowserWindow
├── preload.js       contextBridge – exposes electronAPI to renderer (store, IPC events)
├── backend/
│   ├── main.py      FastAPI app: CORS + router registration + /health endpoint
│   └── routers/     One file per domain:
│       ├── api_key.py       POST /api/key/validate
│       ├── employee.py      /api/employee/upload|save|list
│       ├── audio.py         /api/audio/devices|upload
│       ├── stt.py           /stt/process|progress(SSE)|result|cancel
│       ├── pseudonymize.py  /pseudonymize/process  (AliasRegistry + rapidfuzz + NER)
│       ├── llm.py           /llm/default-prompt|generate(SSE)  (Claude/GPT/Gemini)
│       └── output.py        /output/restore|export-docx  +  /session/clear
├── frontend/
│   ├── index.html   Shell: stage indicator + #app-content + footer nav
│   ├── css/style.css   Design tokens as CSS variables
│   ├── js/
│   │   ├── app.js   Stage router: fetches HTML fragments into #app-content
│   │   └── api.js   Fetch wrapper for all FastAPI endpoints (apiFetch → namespaces)
│   └── pages/       Per-stage HTML fragments (inline <script> for page-local logic)
│       ├── stage1-apikey.html       Stage 1: API keys + HF token
│       ├── stage2-employee.html     Stage 2: employee DB upload
│       ├── meeting-info.html        Stage 3: meeting metadata + attendees
│       ├── stt.html                 Stage 5: audio upload + STT progress
│       ├── speaker-assign.html      Stage 6: speaker→person mapping
│       ├── pseudonymize-preview.html Stage 7: anonymization review
│       ├── generate.html            Stage 8: LLM streaming generation
│       └── result.html              Stage 9: real-name restore + .txt/.docx export
├── models/          Git-ignored; populated by setup.py
└── setup.py         Downloads Whisper medium, KLUE-BERT into models/
```

### Key Patterns

**Stage system (`app.js`):** 11 stages defined in `STAGES[]`. `goToStage(n)` fetches the HTML fragment and injects it into `#app-content`. Inline `<script>` tags are re-executed manually via `createElement('script')` (innerHTML doesn't run scripts). Pages expose optional hooks:
- `window.onPageLoad()` – called after injection
- `window.onNextValidate()` – called on NEXT click; must return `false` to block navigation (supports async)

**Cross-stage data:** Pages store results in global `window.*` variables:
- `window.sttResult` — STT segments from Stage 5
- `window.meetingInfo` — form data from Stage 3
- `window.speakerMapping` — SPEAKER_XX → name dict from Stage 6
- `window.pseudonymResult` — `{anonymized_segments, mapping_table, stats}` from Stage 7
- `window.generatedMinutes` — LLM output text from Stage 8

**LLM streaming:** `LLM.stream()` in `api.js` uses `fetch` + `ReadableStream` (not EventSource — doesn't support POST). SSE buffer parsed on `\n\n` separator; events are `{type:"chunk"|"done"|"error"}`.

**Session security:** `pseudonymize._session_mapping` (alias→original dict) lives only in memory. It is cleared on Word export (`output.py`) and on app quit (`main.js` `before-quit`).

**IPC:** Renderer accesses `window.electronAPI.store.{get,set,delete}` for persistent config (API keys stored via `electron-store`). Backend readiness signalled via `backend:ready` / `backend:error` IPC events.

**API layer (`api.js`) namespaces:** `ApiKey`, `Employee`, `Audio`, `STT`, `Pseudonymize`, `LLM`, `Output`, `Minutes`(legacy).

## Design System

CSS variables in `frontend/css/style.css`:

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
- `electron-store` (not backend) holds API keys — they never leave the device.
- The CSP in `index.html` includes `'unsafe-inline'` for `script-src` — required for injected page fragment scripts.
