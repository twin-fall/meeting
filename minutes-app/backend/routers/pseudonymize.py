"""
pseudonymize.py - 3단계 가명처리 라우터

엔드포인트:
  POST /pseudonymize/process  - STT 세그먼트 가명처리 실행

처리 흐름:
  1단계) rapidfuzz 퍼지 매칭 (임계값 85%) — STT 오타 흡수
  2단계) 사원명부 전수 매칭 (정확 + 퍼지)
  3단계) KLUE-BERT NER 보조 감지 (놓친 인명/조직명)

매핑 테이블은 세션 메모리에만 존재하며 앱 종료 시 자동 소멸합니다.
"""

import os
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ── 세션 메모리 — 파일로 저장 절대 금지 ──────────────────
_session_mapping: dict[str, str] = {}   # alias → original

# ── NER 모델 캐시 ─────────────────────────────────────────
_ner_pipeline = None
_ner_lock = __import__("threading").Lock()


# ── Pydantic 모델 ─────────────────────────────────────────

class Segment(BaseModel):
    speaker: str
    start: float
    end: float
    text: str


class Person(BaseModel):
    name: str = ""
    dept: str = ""
    position: str = ""


class ProcessRequest(BaseModel):
    segments: list[Segment]
    participants: list[Person]
    employee_db: list[Person]
    speaker_mapping: dict[str, Optional[str]]   # SPEAKER_XX → name | null


# ── AliasRegistry ─────────────────────────────────────────

class AliasRegistry:
    """발견 순서대로 [사람N] / [직위N] / [팀N] 별칭을 할당합니다."""

    def __init__(self):
        self._reverse: dict[str, str] = {}   # original → alias
        self._map: dict[str, str] = {}        # alias → original
        self._cnt = {"person": 0, "position": 0, "org": 0}

    def _get(self, category: str, original: str) -> str:
        if original in self._reverse:
            return self._reverse[original]
        self._cnt[category] += 1
        n = self._cnt[category]
        label = {"person": "사람", "position": "직위", "org": "팀"}[category]
        alias = f"[{label}{n}]"
        self._reverse[original] = alias
        self._map[alias] = original
        return alias

    def person(self, name: str) -> str:
        return self._get("person", name)

    def position(self, pos: str) -> str:
        return self._get("position", pos)

    def org(self, dept: str) -> str:
        return self._get("org", dept)

    @property
    def mapping_table(self) -> dict[str, str]:
        return dict(self._map)


# ── 퍼지 치환 ──────────────────────────────────────────────

def _fuzzy_replace(text: str, target: str, alias: str, threshold: int = 85) -> tuple[str, int]:
    """
    text 안에서 target과 유사도 >= threshold 인 슬라이딩 윈도우를 찾아
    alias로 치환합니다. 긴 매치를 우선합니다.
    (오른쪽→왼쪽 순 치환으로 인덱스 보존)
    """
    from rapidfuzz import fuzz

    tlen = len(target)
    if tlen < 2:
        return text, 0

    spans: list[tuple[int, int]] = []   # (start, end) 치환 예정 구간

    for window_size in range(tlen + 1, max(1, tlen - 2) - 1, -1):
        i = 0
        while i <= len(text) - window_size:
            # 이미 포함된 구간 건너뜀
            if any(s <= i < e for s, e in spans):
                i += 1
                continue
            window = text[i : i + window_size]
            if fuzz.ratio(window, target) >= threshold:
                spans.append((i, i + window_size))
                i += window_size
            else:
                i += 1

    if not spans:
        return text, 0

    # 오른쪽부터 치환
    spans.sort(key=lambda x: x[0], reverse=True)
    for start, end in spans:
        text = text[:start] + alias + text[end:]

    return text, len(spans)


# ── NER 로드 ───────────────────────────────────────────────

def _load_ner() -> object | None:
    """KLUE-BERT NER 파이프라인 로드 (실패 시 None 반환)."""
    global _ner_pipeline
    if _ner_pipeline is not None:
        return _ner_pipeline
    with _ner_lock:
        if _ner_pipeline is not None:
            return _ner_pipeline
        try:
            from transformers import pipeline as hf_pipeline

            model_dir = os.path.join(
                os.path.dirname(__file__), "..", "..", "models", "klue-bert"
            )
            if not os.path.isdir(model_dir):
                return None
            _ner_pipeline = hf_pipeline(
                "ner",
                model=model_dir,
                tokenizer=model_dir,
                aggregation_strategy="simple",
                device=-1,   # CPU
            )
        except Exception:
            _ner_pipeline = None
    return _ner_pipeline


def _run_ner(texts: list[str]) -> list[list[dict]]:
    """텍스트 목록에 NER 실행. 실패 시 빈 결과 반환."""
    ner = _load_ner()
    if ner is None:
        return [[] for _ in texts]
    try:
        return [ner(t) for t in texts]
    except Exception:
        return [[] for _ in texts]


# ── 메인 엔드포인트 ────────────────────────────────────────

@router.post("/process")
async def process(req: ProcessRequest):
    global _session_mapping

    reg = AliasRegistry()

    # ── 참석자 별칭 사전 등록 (번호 순서 고정) ──────────────
    for p in req.participants:
        if p.name:
            reg.person(p.name)
        if p.position:
            reg.position(p.position)
        if p.dept:
            reg.org(p.dept)

    # ── 화자 ID → 사람 별칭 매핑 ────────────────────────────
    speaker_aliases: dict[str, str] = {}
    for spk_id, name in req.speaker_mapping.items():
        if name and name.strip():
            speaker_aliases[spk_id] = reg.person(name.strip())

    # ── 치환 대상 엔티티 구성 ─────────────────────────────────
    # 참석자 우선, 사원명부 보충 (긴 이름 먼저 치환)
    seen_names: set[str] = set()
    names_to_replace: list[str] = []

    for p in req.participants + req.employee_db:
        n = (p.name or "").strip()
        if n and n not in seen_names:
            names_to_replace.append(n)
            seen_names.add(n)

    names_to_replace.sort(key=len, reverse=True)

    positions_to_replace = sorted(
        {(p.position or "").strip() for p in req.participants if p.position},
        key=len, reverse=True,
    )
    depts_to_replace = sorted(
        {(p.dept or "").strip() for p in req.participants if p.dept},
        key=len, reverse=True,
    )

    # ── 세그먼트별 처리 ──────────────────────────────────────
    anonymized: list[dict] = []
    total_replaced = 0

    for seg in req.segments:
        text = seg.text
        speaker = speaker_aliases.get(seg.speaker, seg.speaker)
        cnt = 0

        # 1·2단계: 퍼지 매칭 (이름 → 직위 → 소속 순서로 적용)
        for name in names_to_replace:
            text, n = _fuzzy_replace(text, name, reg.person(name), threshold=85)
            cnt += n

        for pos in positions_to_replace:
            text, n = _fuzzy_replace(text, pos, reg.position(pos), threshold=87)
            cnt += n

        for dept in depts_to_replace:
            text, n = _fuzzy_replace(text, dept, reg.org(dept), threshold=87)
            cnt += n

        total_replaced += cnt
        anonymized.append(
            {"speaker": speaker, "start": seg.start, "end": seg.end, "text": text}
        )

    # ── 3단계: NER 보조 ──────────────────────────────────────
    # 아직 치환되지 않은 인명·조직명을 감지해 uncertain_items에 기록
    plain_texts = [s["text"] for s in anonymized]
    ner_results = _run_ner(plain_texts)

    uncertain_items: list[str] = []
    for ner_list in ner_results:
        for ent in ner_list:
            etype = ent.get("entity_group", "")
            word  = (ent.get("word") or "").strip()
            if etype in ("PER", "ORG") and word and word not in uncertain_items:
                # 이미 치환된 별칭([사람N] 등) 제외
                if not re.match(r"^\[.+\d+\]$", word):
                    uncertain_items.append(word)

    # 세션 메모리에 저장 (파일 저장 금지)
    _session_mapping = reg.mapping_table

    return {
        "anonymized_segments": anonymized,
        "mapping_table": reg.mapping_table,
        "stats": {
            "replaced_count": total_replaced,
            "uncertain_count": len(uncertain_items),
            "uncertain_items": uncertain_items,
        },
    }
