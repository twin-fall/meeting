/**
 * api.js - FastAPI 백엔드(localhost:8765) 호출 유틸리티
 */

const API_BASE = 'http://127.0.0.1:8765';

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

  /** 업로드 파싱 결과와 컬럼 매핑을 함께 저장 (rows 포함 버전) */
  saveWithRows(mapping, rows) {
    return apiFetch('/api/employee/save', {
      method: 'POST',
      body: JSON.stringify({ mapping, rows }),
    });
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

// ── 가명처리 ─────────────────────────────────────────

const Pseudonymize = {
  /**
   * STT 세그먼트 + 참석자 + 사원명부 + 화자 매핑을 전송해 가명처리 실행.
   * @param {object} payload - { segments, participants, employee_db, speaker_mapping }
   */
  process(payload) {
    return apiFetch('/pseudonymize/process', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};

// ── LLM 회의록 생성 (SSE 스트리밍) ──────────────────────

const LLM = {
  /**
   * 기본 시스템 프롬프트를 백엔드에서 가져옵니다.
   */
  defaultPrompt() {
    return apiFetch('/llm/default-prompt');
  },

  /**
   * POST /llm/generate 를 fetch 스트리밍으로 호출.
   * EventSource는 POST를 지원하지 않으므로 fetch + ReadableStream 방식을 사용.
   *
   * @param {object}   payload       - GenerateRequest 본문
   * @param {Function} onChunk       - (text: string) => void
   * @param {Function} onDone        - (totalTokens: number) => void
   * @param {Function} onError       - (message: string) => void
   * @param {AbortSignal} signal     - AbortController.signal
   */
  async stream(payload, { onChunk, onDone, onError, signal } = {}) {
    let response;
    try {
      response = await fetch(`${API_BASE}/llm/generate`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
        signal,
      });
    } catch (err) {
      if (err.name === 'AbortError') return;
      throw new Error('서버에 연결할 수 없습니다. 앱을 다시 시작해 주세요.');
    }

    if (!response.ok) {
      let detail = '알 수 없는 오류가 발생했습니다.';
      try { detail = (await response.json()).detail || detail; } catch { /* ignore */ }
      throw new Error(detail);
    }

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE 이벤트 구분자 '\n\n' 단위로 파싱
        let sepIdx;
        while ((sepIdx = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0, sepIdx);
          buffer      = buffer.slice(sepIdx + 2);

          for (const line of block.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            const raw = line.slice(6).trim();
            if (!raw) continue;
            let data;
            try { data = JSON.parse(raw); } catch { continue; }

            if (data.type === 'chunk' && onChunk)   onChunk(data.content  ?? '');
            if (data.type === 'done'  && onDone)    onDone(data.total_tokens ?? 0);
            if (data.type === 'error' && onError)   onError(data.message  ?? '오류 발생');
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError' && onError) onError(err.message);
    }
  },
};

// ── 실명 복원 & 출력 ──────────────────────────────────────

const Output = {
  /**
   * 가명 텍스트에서 실명을 복원합니다.
   * @param {string} anonymizedText
   * @param {Object} mappingTable  alias → original
   */
  restore(anonymizedText, mappingTable) {
    return apiFetch('/output/restore', {
      method: 'POST',
      body: JSON.stringify({ anonymized_text: anonymizedText, mapping_table: mappingTable }),
    });
  },

  /**
   * Word(.docx) 파일을 생성하고 브라우저 다운로드를 트리거합니다.
   * @param {Object} payload  ExportRequest 필드
   */
  async downloadDocx(payload) {
    let response;
    try {
      response = await fetch(`${API_BASE}/output/export-docx`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      });
    } catch {
      throw new Error('서버에 연결할 수 없습니다. 앱을 다시 시작해 주세요.');
    }
    if (!response.ok) {
      let detail = '문서 생성에 실패했습니다.';
      try { detail = (await response.json()).detail || detail; } catch { /* ignore */ }
      throw new Error(detail);
    }
    const blob = await response.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');

    // Content-Disposition 헤더에서 파일명 추출 시도
    const cd = response.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename\*?=(?:UTF-8'')?([^;]+)/i);
    a.download = match ? decodeURIComponent(match[1].replace(/"/g, '')) : 'minutes.docx';
    a.href = url;
    a.click();
    URL.revokeObjectURL(url);
  },

  /** 세션 가명처리 매핑 소거 */
  clearSession() {
    return apiFetch('/session/clear', { method: 'DELETE' });
  },
};

// ── 회의록 생성 (레거시 stub) ──────────────────────────────

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
