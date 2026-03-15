"""
stt.py - STT(음성인식) + 화자 분리 라우터

엔드포인트:
  POST /stt/process   - 파일 업로드 후 백그라운드 처리 시작
  GET  /stt/progress  - SSE 진행률 스트리밍
  GET  /stt/result    - 처리 결과 조회
  POST /stt/cancel    - 처리 취소 요청
"""

import asyncio
import json
import os
import tempfile
import threading
import time
from typing import AsyncGenerator

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter()

# ── 지원 확장자 ─────────────────────────────────────────────────────────────
SUPPORTED_EXT = {".m4a", ".mp3", ".aac", ".wav", ".flac", ".mp4", ".webm"}

# ── 모델 캐시 (프로세스 생존 동안 1회만 로드) ──────────────────────────────
_whisper_model = None
_diarization_pipeline = None
_model_lock = threading.Lock()

# ── 처리 상태 (단일 작업 가정) ──────────────────────────────────────────────
_state: dict = {
    "stage": "대기 중",
    "percent": 0,
    "running": False,
    "cancel": False,
    "result": None,
    "error": None,
}


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────────

def _set_progress(stage: str, percent: int) -> None:
    _state["stage"] = stage
    _state["percent"] = min(max(percent, 0), 100)


def _load_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _model_lock:
        if _whisper_model is not None:
            return _whisper_model
        from faster_whisper import WhisperModel

        models_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "models", "whisper"
        )
        os.makedirs(models_dir, exist_ok=True)
        _whisper_model = WhisperModel(
            "medium",
            device="cpu",
            compute_type="int8",
            download_root=models_dir,
        )
    return _whisper_model


def _load_diarization(hf_token: str):
    global _diarization_pipeline
    if _diarization_pipeline is not None:
        return _diarization_pipeline
    with _model_lock:
        if _diarization_pipeline is not None:
            return _diarization_pipeline

        from pyannote.audio import Pipeline

        models_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "models", "pyannote"
        )
        os.makedirs(models_dir, exist_ok=True)
        os.environ["PYANNOTE_CACHE"] = models_dir

        kwargs = {}
        if hf_token:
            kwargs["use_auth_token"] = hf_token

        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", **kwargs
        )
    return _diarization_pipeline


def _merge(stt_segs: list[dict], diar_segs: list[dict]) -> list[dict]:
    """타임스탬프 겹침 기반으로 STT 구간에 화자 레이블 할당."""
    result = []
    for seg in stt_segs:
        best_speaker = "SPEAKER_00"
        best_overlap = 0.0
        for d in diar_segs:
            overlap = max(0.0, min(seg["end"], d["end"]) - max(seg["start"], d["start"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d["speaker"]
        text = (seg["text"] or "").strip()
        if text:
            result.append(
                {
                    "speaker": best_speaker,
                    "start": round(seg["start"], 2),
                    "end": round(seg["end"], 2),
                    "text": text,
                }
            )
    return result


def _run_pipeline(file_path: str, hf_token: str) -> None:
    """백그라운드 스레드에서 실행되는 전체 파이프라인."""
    tmp_to_delete = file_path
    try:
        _state.update({"running": True, "cancel": False, "result": None, "error": None})

        # ── 1단계: 파일 로딩 (0~10%) ──────────────────────────────────────
        _set_progress("파일 로딩 중", 5)
        time.sleep(0.3)
        if _state["cancel"]:
            return

        # ── 2단계: STT (10~60%) ────────────────────────────────────────────
        _set_progress("STT 변환 중", 10)
        whisper = _load_whisper()

        segments_gen, info = whisper.transcribe(
            file_path,
            language="ko",
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        duration: float = getattr(info, "duration", 0) or 1.0
        stt_segs: list[dict] = []

        for seg in segments_gen:
            if _state["cancel"]:
                return
            stt_segs.append({"start": seg.start, "end": seg.end, "text": seg.text})
            pct = 10 + int((seg.end / duration) * 50)
            _set_progress("STT 변환 중", min(pct, 60))

        _set_progress("STT 변환 중", 60)

        # ── 3단계: 화자 분리 (60~90%) ─────────────────────────────────────
        _set_progress("화자 분리 중", 62)
        if _state["cancel"]:
            return

        pipeline = _load_diarization(hf_token)
        diarization = pipeline(file_path)

        diar_segs: list[dict] = [
            {"start": turn.start, "end": turn.end, "speaker": speaker}
            for turn, _, speaker in diarization.itertracks(yield_label=True)
        ]
        _set_progress("화자 분리 중", 90)

        if _state["cancel"]:
            return

        # ── 4단계: 병합 (90~100%) ─────────────────────────────────────────
        _set_progress("결과 병합 중", 92)
        merged = _merge(stt_segs, diar_segs)
        speakers = sorted({s["speaker"] for s in merged})

        _set_progress("완료", 100)
        _state["result"] = {
            "segments": merged,
            "speaker_count": len(speakers),
            "duration": round(duration, 2),
        }

    except Exception as exc:
        _state["error"] = f"처리 중 오류가 발생했습니다: {exc}"
        _set_progress("오류", _state["percent"])
    finally:
        _state["running"] = False
        # 임시 파일 삭제
        try:
            if os.path.exists(tmp_to_delete):
                os.unlink(tmp_to_delete)
        except OSError:
            pass


# ── 엔드포인트 ───────────────────────────────────────────────────────────────

@router.post("/process")
async def process_audio(
    file: UploadFile = File(...),
    hf_token: str = Form(""),
):
    """음성 파일 업로드 후 STT + 화자 분리 처리 시작."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(sorted(SUPPORTED_EXT))}",
        )

    if _state["running"]:
        raise HTTPException(status_code=409, detail="이미 처리 중인 작업이 있습니다.")

    # 임시 파일로 저장
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    thread = threading.Thread(
        target=_run_pipeline,
        args=(tmp_path, hf_token),
        daemon=True,
    )
    thread.start()

    return {"status": "processing", "message": "처리를 시작했습니다."}


@router.get("/progress")
async def get_progress():
    """SSE: 실시간 진행률 스트리밍."""

    async def _generate() -> AsyncGenerator[str, None]:
        while True:
            payload = json.dumps(
                {
                    "stage": _state["stage"],
                    "percent": _state["percent"],
                    "running": _state["running"],
                    "error": _state["error"],
                    "done": _state["result"] is not None,
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"

            # 완료 또는 오류 시 스트림 종료
            if not _state["running"] and (
                _state["result"] is not None or _state["error"] is not None
            ):
                break

            await asyncio.sleep(0.4)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/result")
async def get_result():
    """마지막 처리 결과 반환."""
    if _state["error"]:
        raise HTTPException(status_code=500, detail=_state["error"])
    if _state["result"] is None:
        raise HTTPException(status_code=404, detail="처리 결과가 없습니다.")
    return _state["result"]


@router.post("/cancel")
async def cancel_processing():
    """진행 중인 처리 취소 요청."""
    if not _state["running"]:
        raise HTTPException(status_code=400, detail="처리 중인 작업이 없습니다.")
    _state["cancel"] = True
    return {"status": "cancel_requested", "message": "취소 요청이 접수되었습니다."}
