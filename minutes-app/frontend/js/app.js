/**
 * app.js - 단계 전환 및 페이지 라우팅 로직
 *
 * 총 11단계:
 *  1. API 키 설정
 *  2. 사원명부 업로드
 *  3. 회의 정보 + 참석자    meeting-info.html
 *  4. 음성 입력 방식        (추후 구현)
 *  5. 음성 업로드 + STT     stt.html
 *  6. 화자 배정             speaker-assign.html
 *  7. 가명처리              pseudonymize-preview.html
 *  8. 회의록 생성           (추후 구현)
 *  9. 회의록 편집           (추후 구현)
 * 10. 내보내기              (추후 구현)
 * 11. 완료                  (추후 구현)
 */

const STAGES = [
  { id: 1,  label: '①', title: 'API SETUP',   page: 'pages/stage1-apikey.html' },
  { id: 2,  label: '②', title: 'EMPLOYEE DB', page: 'pages/stage2-employee.html' },
  { id: 3,  label: '③', title: 'MEETING INFO', page: 'pages/meeting-info.html' },
  { id: 4,  label: '④', title: 'AUDIO MODE',  page: 'pages/stage-wip.html' },
  { id: 5,  label: '⑤', title: 'UPLOAD',      page: 'pages/stt.html' },
  { id: 6,  label: '⑥', title: 'SPEAKER MAP', page: 'pages/speaker-assign.html' },
  { id: 7,  label: '⑦', title: 'ANONYMIZE',   page: 'pages/pseudonymize-preview.html' },
  { id: 8,  label: '⑧', title: 'GENERATE',    page: 'pages/stage-wip.html' },
  { id: 9,  label: '⑨', title: 'EDIT',        page: 'pages/stage-wip.html' },
  { id: 10, label: '⑩', title: 'EXPORT',      page: 'pages/stage-wip.html' },
  { id: 11, label: '⑪', title: 'DONE',        page: 'pages/stage-wip.html' },
];

let currentStage = 1;

// ── 초기화 ─────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderStageIndicator();
  goToStage(1);

  document.getElementById('btn-next').addEventListener('click', nextStage);
  document.getElementById('btn-prev').addEventListener('click', prevStage);

  // Electron IPC 이벤트
  if (window.electronAPI) {
    window.electronAPI.onBackendReady(() => {
      document.getElementById('loading-overlay').classList.add('hidden');
    });
    window.electronAPI.onBackendError((msg) => {
      document.getElementById('loading-overlay').classList.add('hidden');
      showGlobalError(msg);
    });
  } else {
    // 브라우저 개발용: 오버레이 바로 숨김
    document.getElementById('loading-overlay').classList.add('hidden');
  }
});

// ── 단계 인디케이터 렌더 ────────────────────────────

function renderStageIndicator() {
  const el = document.getElementById('stage-indicator');
  el.innerHTML = STAGES.map((s) => `
    <div class="stage-dot ${s.id === currentStage ? 'active' : s.id < currentStage ? 'done' : ''}"
         id="stage-dot-${s.id}"
         title="${s.title}">
      ${s.label}
    </div>
  `).join('');
}

// ── 페이지 로드 ─────────────────────────────────────

async function goToStage(stageId) {
  currentStage = stageId;
  renderStageIndicator();
  updateNavButtons();

  const stage = STAGES.find((s) => s.id === stageId);
  const content = document.getElementById('app-content');

  try {
    const res = await fetch(stage.page);
    if (!res.ok) throw new Error(`페이지를 불러올 수 없습니다: ${stage.page}`);
    const html = await res.text();
    content.innerHTML = html;

    // innerHTML은 <script>를 실행하지 않으므로 수동 실행
    content.querySelectorAll('script').forEach((old) => {
      const s = document.createElement('script');
      s.textContent = old.textContent;
      document.body.appendChild(s);
      document.body.removeChild(s);
    });

    // 페이지 스크립트 초기화 훅
    if (typeof window.onPageLoad === 'function') {
      window.onPageLoad();
      window.onPageLoad = null;
    }
  } catch (e) {
    content.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

// ── 네비게이션 ──────────────────────────────────────

async function nextStage() {
  // 현재 페이지의 유효성 검사 훅 (동기/비동기 모두 지원)
  if (typeof window.onNextValidate === 'function') {
    const valid = await Promise.resolve(window.onNextValidate());
    if (!valid) return;
    window.onNextValidate = null;
  }
  if (currentStage < STAGES.length) goToStage(currentStage + 1);
}

function prevStage() {
  if (currentStage > 1) goToStage(currentStage - 1);
}

function updateNavButtons() {
  const btnPrev = document.getElementById('btn-prev');
  const btnNext = document.getElementById('btn-next');
  btnPrev.style.display = currentStage > 1 ? 'inline-block' : 'none';
  btnNext.textContent   = currentStage === STAGES.length ? 'FINISH ✓' : 'NEXT →';
}

// ── 전역 에러 표시 ──────────────────────────────────

function showGlobalError(message) {
  const el = document.createElement('div');
  el.className = 'alert alert-error';
  el.style.cssText = 'position:fixed;top:72px;left:50%;transform:translateX(-50%);z-index:500;min-width:320px;max-width:600px;';
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

// 외부 링크 클릭 처리 (Electron에서 기본 브라우저로 열기)
document.addEventListener('click', (e) => {
  const link = e.target.closest('a[data-external]');
  if (link && window.electronAPI?.openExternal) {
    e.preventDefault();
    window.electronAPI.openExternal(link.href);
  }
});
