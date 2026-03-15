/**
 * app.js - 단계 전환 및 페이지 라우팅 로직
 *
 * 총 11단계:
 *  1. API 키 설정
 *  2. 사원명부 업로드
 *  3. 회의 기본정보 입력    (추후 구현)
 *  4. 음성 입력 방식 선택   (추후 구현)
 *  5. 음성 업로드 + STT     stt.html
 *  6. 화자 매핑             (추후 구현)
 *  7. 스크립트 검토         (추후 구현)
 *  8. 스크립트 검토         (추후 구현)
 *  9. 회의록 생성           (추후 구현)
 * 10. 회의록 편집           (추후 구현)
 * 11. 내보내기              (추후 구현)
 */

const STAGES = [
  { id: 1,  label: '①', title: 'API SETUP',   page: 'pages/stage1-apikey.html' },
  { id: 2,  label: '②', title: 'EMPLOYEE DB', page: 'pages/stage2-employee.html' },
  { id: 3,  label: '③', title: 'MEETING INFO',page: 'pages/stage-wip.html' },
  { id: 4,  label: '④', title: 'AUDIO MODE',  page: 'pages/stage-wip.html' },
  { id: 5,  label: '⑤', title: 'UPLOAD',      page: 'pages/stt.html' },
  { id: 6,  label: '⑥', title: 'SPEAKER MAP', page: 'pages/stage-wip.html' },
  { id: 7,  label: '⑦', title: 'SCRIPT',      page: 'pages/stage-wip.html' },
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

function nextStage() {
  // 현재 페이지의 유효성 검사 훅
  if (typeof window.onNextValidate === 'function') {
    const valid = window.onNextValidate();
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
