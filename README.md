# 회의록 자동작성 앱

인사팀 회의 음성을 자동으로 전사·가명처리·회의록 생성까지 처리하는 Windows 데스크탑 앱입니다.

## 기술 스택

| 계층 | 사용 기술 |
|------|-----------|
| 데스크탑 셸 | Electron 28 |
| 백엔드 API | FastAPI 0.111 + Uvicorn (포트 8765) |
| STT | faster-whisper medium (한국어) |
| 화자 분리 | pyannote/speaker-diarization-3.1 |
| 가명처리 | rapidfuzz + KLUE-BERT NER |
| LLM | Anthropic Claude / OpenAI GPT / Google Gemini |
| Word 출력 | python-docx |

---

## 설치 & 실행

### 사전 요구사항

- Python 3.10+
- Node.js 18+
- CUDA 지원 GPU (권장) 또는 CPU

### 1. Python 의존성 설치

```bash
cd minutes-app/backend
pip install -r requirements.txt
```

### 2. AI 모델 다운로드

```bash
cd minutes-app
python setup.py
```

> faster-whisper medium 모델과 KLUE-BERT NER 모델을 `models/` 디렉터리에 다운로드합니다.
> pyannote 화자 분리 모델은 HuggingFace 토큰이 필요하며 앱 실행 후 Stage 1에서 입력합니다.

### 3. Node.js 의존성 설치

```bash
cd minutes-app
npm install
```

### 4. 앱 실행

```bash
npm start
```

---

## 11단계 워크플로우

| 단계 | 이름 | 설명 |
|------|------|------|
| 1 | API SETUP | LLM API 키 + HuggingFace 토큰 입력 및 검증 |
| 2 | EMPLOYEE DB | 사원명부 xlsx/csv 업로드 및 컬럼 매핑 |
| 3 | MEETING INFO | 회의 일시·장소·종류·안건 입력 + 참석자 선택 |
| 4 | AUDIO MODE | (향후 구현) |
| 5 | UPLOAD | 음성 파일 업로드 → STT + 화자 분리 실행 |
| 6 | SPEAKER MAP | 화자 ID별 실제 참석자 이름 매핑 |
| 7 | ANONYMIZE | 3단계 가명처리 (퍼지 매칭 → 사원명부 → NER) |
| 8 | GENERATE | LLM 스트리밍으로 회의록 초안 생성 |
| 9 | RESULT | 실명 복원 + 편집 + .txt/.docx 내보내기 |
| 10–11 | — | (향후 구현) |

---

## 프로젝트 구조

```
minutes-app/
├── main.js              # Electron 진입점 — 백엔드 프로세스 관리
├── preload.js           # contextBridge IPC 노출
├── package.json
├── setup.py             # AI 모델 초기 다운로드
├── frontend/
│   ├── index.html       # 앱 셸 (CSP, 스타일, 내비게이션)
│   ├── css/style.css    # 디자인 시스템
│   ├── js/
│   │   ├── app.js       # 11단계 SPA 라우터
│   │   └── api.js       # FastAPI 클라이언트 네임스페이스
│   └── pages/           # 단계별 HTML 프래그먼트
│       ├── stage1-apikey.html
│       ├── stage2-employee.html
│       ├── meeting-info.html
│       ├── stt.html
│       ├── speaker-assign.html
│       ├── pseudonymize-preview.html
│       ├── generate.html
│       └── result.html
└── backend/
    ├── main.py          # FastAPI 앱 + 라우터 등록
    ├── requirements.txt
    └── routers/
        ├── api_key.py       # POST /api/key/validate
        ├── employee.py      # /api/employee/upload|save|list
        ├── audio.py         # /api/audio/devices|upload
        ├── stt.py           # /stt/process|progress|result|cancel
        ├── pseudonymize.py  # /pseudonymize/process
        ├── llm.py           # /llm/default-prompt|generate (SSE)
        └── output.py        # /output/restore|export-docx, /session/clear
```

---

## API 키 준비

앱 사용 전 아래 키 중 하나 이상을 준비하세요.

| 제공사 | 키 발급 주소 | 용도 |
|--------|-------------|------|
| Anthropic | console.anthropic.com | Claude 모델 |
| OpenAI | platform.openai.com | GPT 모델 |
| Google | aistudio.google.com | Gemini 모델 |
| HuggingFace | huggingface.co/settings/tokens | 화자 분리 모델 다운로드 |

---

## 보안 & 개인정보

- **API 키**는 electron-store(로컬 암호화 스토리지)에만 저장됩니다.
- **가명처리 매핑 테이블**은 세션 메모리에만 존재하며 파일로 저장되지 않습니다.
- 앱 종료 또는 Word 내보내기 완료 시 매핑이 즉시 소거됩니다.
- 음성 파일 및 전사 결과는 로컬 백엔드에서만 처리됩니다.

---

## 빌드 (Windows 설치 파일)

```bash
cd minutes-app
npm run build
```

`dist/` 디렉터리에 NSIS 설치 파일이 생성됩니다.
