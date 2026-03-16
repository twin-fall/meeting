"""
llm.py - LLM API 스트리밍 라우터

엔드포인트:
  GET  /llm/default-prompt    - 기본 시스템 프롬프트 반환
  POST /llm/generate          - SSE 스트리밍 회의록 생성

지원 모델:
  Claude : claude-sonnet-4-20250514  (anthropic 패키지)
  GPT    : gpt-4o                    (openai 패키지)
  Gemini : gemini-1.5-pro            (google-generativeai 패키지)

보안:
  - API 키는 절대 로그에 출력하지 않음
  - 원본 성명 포함 여부 사전 검증 후 전송
"""

import asyncio
import json
from typing import AsyncGenerator, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

# ── 기본 시스템 프롬프트 ──────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """\
당신은 인사팀 회의록 작성 전문가입니다.
아래 규칙을 반드시 따르세요.

[문체 규칙]
- 모든 문장은 '~했음', '~논의함', '~결정함', '~검토 예정임'으로 종결
- 1인칭 주어 제거
- 구어체를 문어체로 자연스럽게 변환

[구조 규칙]
- 회의 종류에 따라 섹션 구성:
  * 노사협의회: Intro / 협의사항 / 공지사항
  * 인사위원회: Intro / PT 질의응답 및 선발 Summary / 최종 선발 결과
  * 팀 회의: Intro / 논의내용 / 결정사항 / Action Items
  * 기타: Intro / 논의내용
- 발화자 형식: (이름) 으로 시작
- 중복/잡음 발화 정리"""

# ── Pydantic 모델 ─────────────────────────────────────────

class MeetingInfo(BaseModel):
    datetime: str = ""
    location: str = ""
    type: str = ""
    agenda: str = ""


class Participant(BaseModel):
    name: str = ""
    dept: str = ""
    position: str = ""


class GenerateRequest(BaseModel):
    provider: str                          # claude | gpt | gemini
    api_key: str
    anonymized_segments: list[dict]
    meeting_info: MeetingInfo
    participants: list[Participant] = []
    system_prompt: Optional[str] = None    # None → 기본값 사용
    original_names: list[str] = []         # 사전 검증용 원본 성명 목록


# ── 유틸리티 ──────────────────────────────────────────────

def _validate_no_originals(segments: list[dict], original_names: list[str]) -> int:
    """세그먼트 텍스트에 원본 성명이 남아있으면 발견 건수 반환."""
    count = 0
    for name in original_names:
        if len(name) < 2:
            continue
        for seg in segments:
            text    = seg.get("text", "")    or ""
            speaker = seg.get("speaker", "") or ""
            if name in text or name in speaker:
                count += 1
                break
    return count


def _build_user_prompt(req: GenerateRequest) -> str:
    mi = req.meeting_info

    # 참석자 섹션
    participant_lines = []
    for p in req.participants:
        parts = [p.name or ""]
        if p.position:
            parts.append(p.position)
        if p.dept:
            parts.append(p.dept)
        participant_lines.append("- " + " / ".join(filter(None, parts)))
    participants_text = "\n".join(participant_lines) if participant_lines else "- (미입력)"

    # 발화 기록 (연속 동일 화자 병합)
    transcript_lines: list[str] = []
    prev_speaker: Optional[str] = None
    current_texts: list[str] = []

    for seg in req.anonymized_segments:
        speaker = (seg.get("speaker") or "?").strip()
        text    = (seg.get("text")    or "").strip()
        if not text:
            continue
        if speaker == prev_speaker:
            current_texts.append(text)
        else:
            if prev_speaker is not None and current_texts:
                transcript_lines.append(f"({prev_speaker}): {' '.join(current_texts)}")
            prev_speaker   = speaker
            current_texts  = [text]

    if prev_speaker is not None and current_texts:
        transcript_lines.append(f"({prev_speaker}): {' '.join(current_texts)}")

    transcript_text = "\n".join(transcript_lines) if transcript_lines else "(발화 기록 없음)"

    return f"""회의 정보:
- 일시: {mi.datetime}
- 장소: {mi.location}
- 종류: {mi.type}
- 안건: {mi.agenda}

참석자:
{participants_text}

회의 발화 기록:
{transcript_text}

위 내용을 바탕으로 회의록을 작성해 주세요."""


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── LLM 스트리밍 어댑터 ───────────────────────────────────

async def _stream_claude(
    api_key: str, system_prompt: str, user_prompt: str
) -> AsyncGenerator[tuple[str, object], None]:
    try:
        import anthropic
    except ImportError:
        yield "error", "anthropic 패키지가 설치되지 않았습니다. pip install anthropic"
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=8096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield "chunk", text
            final = await stream.get_final_message()
            total = (final.usage.input_tokens or 0) + (final.usage.output_tokens or 0)
        yield "done", total
    except Exception as exc:
        msg = str(exc)
        if api_key and api_key in msg:
            msg = "Claude API 호출 오류가 발생했습니다."
        yield "error", msg


async def _stream_gpt(
    api_key: str, system_prompt: str, user_prompt: str
) -> AsyncGenerator[tuple[str, object], None]:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield "error", "openai 패키지가 설치되지 않았습니다. pip install openai"
        return

    client = AsyncOpenAI(api_key=api_key)
    total_tokens = 0
    try:
        stream = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield "chunk", chunk.choices[0].delta.content
            if getattr(chunk, "usage", None):
                total_tokens = chunk.usage.total_tokens or 0
        yield "done", total_tokens
    except Exception as exc:
        msg = str(exc)
        if api_key and api_key in msg:
            msg = "OpenAI API 호출 오류가 발생했습니다."
        yield "error", msg


async def _stream_gemini(
    api_key: str, system_prompt: str, user_prompt: str
) -> AsyncGenerator[tuple[str, object], None]:
    try:
        import google.generativeai as genai
    except ImportError:
        yield "error", "google-generativeai 패키지가 설치되지 않았습니다. pip install google-generativeai"
        return

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            system_instruction=system_prompt,
        )
        response = await model.generate_content_async(user_prompt, stream=True)
        async for chunk in response:
            if getattr(chunk, "text", None):
                yield "chunk", chunk.text

        # 스트림 완료 후 토큰 수 조회
        total = 0
        try:
            meta = response.usage_metadata
            total = getattr(meta, "total_token_count", 0) or 0
        except Exception:
            pass
        yield "done", total
    except Exception as exc:
        msg = str(exc)
        if api_key and api_key in msg:
            msg = "Gemini API 호출 오류가 발생했습니다."
        yield "error", msg


# ── 엔드포인트 ───────────────────────────────────────────

@router.get("/default-prompt")
async def get_default_prompt():
    """프론트엔드용 기본 시스템 프롬프트 반환."""
    return {"prompt": DEFAULT_SYSTEM_PROMPT}


@router.post("/generate")
async def generate(req: GenerateRequest):
    """SSE 스트리밍으로 회의록 초안을 생성합니다."""

    # ── 사전 검증: 원본 성명 잔존 여부 ──────────────────────
    violation_count = _validate_no_originals(req.anonymized_segments, req.original_names)
    if violation_count > 0:
        async def _err():
            yield _sse({
                "type": "error",
                "message": (
                    f"가명처리되지 않은 원본 성명이 {violation_count}건 발견되었습니다. "
                    "가명처리 단계로 돌아가 다시 확인해 주세요."
                ),
            })
        return StreamingResponse(
            _err(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    system_prompt = (req.system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT
    user_prompt   = _build_user_prompt(req)

    # ── 제공사별 스트리밍 어댑터 선택 ────────────────────────
    provider = req.provider.lower()
    if provider == "claude":
        adapter = _stream_claude(req.api_key, system_prompt, user_prompt)
    elif provider == "gpt":
        adapter = _stream_gpt(req.api_key, system_prompt, user_prompt)
    elif provider == "gemini":
        adapter = _stream_gemini(req.api_key, system_prompt, user_prompt)
    else:
        async def _unknown():
            yield _sse({"type": "error", "message": f"지원하지 않는 제공사: {req.provider}"})
        return StreamingResponse(
            _unknown(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _generate() -> AsyncGenerator[str, None]:
        try:
            async for event_type, value in adapter:
                if event_type == "chunk":
                    yield _sse({"type": "chunk", "content": value})
                elif event_type == "done":
                    yield _sse({"type": "done", "total_tokens": int(value or 0)})
                elif event_type == "error":
                    yield _sse({"type": "error", "message": str(value)})
                    return
        except asyncio.CancelledError:
            pass  # 클라이언트 연결 종료 — 정상 처리

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
