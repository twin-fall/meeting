/**
 * api.js - FastAPI 백엔드(localhost:8765) 호출 유틸리티
 */

const API_BASE = 'http://localhost:8765';

/**
 * 공통 fetch 래퍼. 에러 시 한국어 메시지를 throw.
 */
async function apiFetch(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...options.headers },
      ...options,
    });
  } catch {
    throw new Error('서버에 연결할 수 없습니다. 앱을 다시 시작해 주세요.');
  }

  if (!response.ok) {
    let detail = '알 수 없는 오류가 발생했습니다.';
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch { /* ignore */ }
    throw new Error(detail);
  }

  return response.json();
}

// ── API 키 ─────────────────────────────────────────

const ApiKey = {
  /** 제공사별 키 유효성 검증 (실제 API 테스트 호출) */
  validate(provider, key) {
    return apiFetch('/api/key/validate', {
      method: 'POST',
      body: JSON.stringify({ provider, key }),
    });
  },
};

// ── 사원명부 ────────────────────────────────────────

const Employee = {
  /** xlsx/csv 파일 업로드 및 파싱 결과 반환 */
  upload(file) {
    const form = new FormData();
    form.append('file', file);
    return apiFetch('/api/employee/upload', {
      method: 'POST',
      headers: {},   // Content-Type은 FormData가 자동 설정
      body: form,
    });
  },

  /** 파싱 결과에 컬럼 매핑 적용 후 JSON 저장 */
  save(mapping) {
    return apiFetch('/api/employee/save', {
      method: 'POST',
      body: JSON.stringify({ mapping }),
    });
  },

  /** 저장된 사원 목록 조회 */
  list() {
    return apiFetch('/api/employee/list');
  },
};

// ── 음성 ────────────────────────────────────────────

const Audio = {
  /** 마이크 장치 목록 조회 */
  devices() {
    return apiFetch('/api/audio/devices');
  },

  /** 음성 파일 업로드 */
  upload(file) {
    const form = new FormData();
    form.append('file', file);
    return apiFetch('/api/audio/upload', {
      method: 'POST',
      headers: {},
      body: form,
    });
  },
};

// ── 음성 인식 & 화자 분리 ─────────────────────────────

const Transcribe = {
  /** STT + 화자 분리 실행 */
  run(audioPath) {
    return apiFetch('/api/transcribe/run', {
      method: 'POST',
      body: JSON.stringify({ audio_path: audioPath }),
    });
  },

  /** 처리 상태 / 진행률 조회 */
  status() {
    return apiFetch('/api/transcribe/status');
  },
};

// ── STT + 화자 분리 ──────────────────────────────────

const STT = {
  /**
   * 음성 파일과 HF 토큰을 multipart로 전송, 백그라운드 처리 시작.
   * @param {File} file - 업로드할 음성 파일
   * @param {string} hfToken - HuggingFace 액세스 토큰
   */
  process(file, hfToken = '') {
    const form = new FormData();
    form.append('file', file);
    form.append('hf_token', hfToken);
    return apiFetch('/stt/process', { method: 'POST', headers: {}, body: form });
  },

  /**
   * SSE EventSource 반환 — 진행률 이벤트를 구독.
   * 각 메시지: { stage, percent, running, error, done }
   * @returns {EventSource}
   */
  progressSource() {
    return new EventSource(`${API_BASE}/stt/progress`);
  },

  /** 처리 완료 결과 조회. */
  result() {
    return apiFetch('/stt/result');
  },

  /** 처리 중 취소 요청. */
  cancel() {
    return apiFetch('/stt/cancel', { method: 'POST' });
  },
};

// ── 회의록 생성 ─────────────────────────────────────

const Minutes = {
  /** LLM 호출로 회의록 초안 생성 */
  generate(payload) {
    return apiFetch('/api/minutes/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  /** DOCX/PDF 내보내기 */
  export(format, content) {
    return apiFetch('/api/minutes/export', {
      method: 'POST',
      body: JSON.stringify({ format, content }),
    });
  },
};
