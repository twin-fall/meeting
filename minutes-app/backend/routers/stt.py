"""
stt.py - STT(음성인식) + 화자 분리 라우터

엔드포인트:
  POST /stt/process   - 파일 업로드 후 백그라운드 처리 시작
  GET  /stt/progress  - SSE 진행률 스트리밍
  GET  /stt/result    - 처리 결과 조회
  POST /stt/cancel    - 처리 취소 요청

환경 요건:
  Python 3.11, torch 2.1.0+cpu, torchaudio 2.1.0+cpu,
  pyannote.audio 3.3.1, av 설치, 회사망 HuggingFace SSL 차단
"""

# ═══════════════════════════════════════════════════════════════════════════
# [COMPAT] torchaudio / torch / torchcodec 호환성 패치
#
# 적용 오류 목록 및 해결 방법:
#   1. torchaudio.set_audio_backend   없음 → dummy 함수
#   2. torchaudio.AudioMetaData       없음 → namedtuple
#   3. torchaudio.list_audio_backends 없음 → ['soundfile'] 반환
#   4. torch.load weights_only 기본값 → False 강제
#   5. torchcodec 미설치             → dummy 모듈 등록
#   6. torchaudio.load/info wav/m4a 실패 → av 기반으로 완전 대체
#   7. av 프레임별 샘플 수 불일치   → numpy.concatenate 로 1D 결합
# ═══════════════════════════════════════════════════════════════════════════

import os
import sys
import types
from collections import namedtuple

# HuggingFace 오프라인 강제 (회사 네트워크 SSL 차단 대응)
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import torch
import torchaudio

# ── 패치 1: torch.load weights_only=False 강제 ─────────────────────────────
_orig_torch_load = torch.load

def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return _orig_torch_load(*args, **kwargs)

torch.load = _patched_torch_load

# ── 패치 2: torchcodec dummy 모듈 등록 ────────────────────────────────────
if "torchcodec" not in sys.modules:
    _tc_mod = types.ModuleType("torchcodec")
    _tc_dec = types.ModuleType("torchcodec.decoders")
    sys.modules["torchcodec"] = _tc_mod
    sys.modules["torchcodec.decoders"] = _tc_dec

# ── 패치 3: torchaudio 누락 API 추가 ──────────────────────────────────────
_AudioMetaData = namedtuple(
    "AudioMetaData",
    ["sample_rate", "num_frames", "num_channels", "bits_per_sample", "encoding"],
)

if not hasattr(torchaudio, "AudioMetaData"):
    torchaudio.AudioMetaData = _AudioMetaData

if not hasattr(torchaudio, "set_audio_backend"):
    torchaudio.set_audio_backend = lambda *a, **kw: None

if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["soundfile"]

# ── 패치 4: torchaudio.load — av 기반 완전 대체 ───────────────────────────
def _av_load(
    path,
    frame_offset: int = 0,
    num_frames: int = -1,
    normalize: bool = True,
    channels_first: bool = True,
    format=None,
    backend=None,
):
    """
    av(PyAV) 기반 오디오 로더.

    핵심 수정:
    - AudioResampler 출력 각 프레임을 1D numpy 배열로 수집 후
      numpy.concatenate 로 결합 → 프레임별 샘플 수 불일치 완전 해결.
    - resampler.resample(None) 으로 내부 버퍼 flush.
    """
    import av
    import numpy as np

    container = av.open(str(path))
    try:
        audio_stream = container.streams.audio[0]
        sr: int = audio_stream.sample_rate

        # fltp(float32 planar) + mono 로 통일 — 채널·포맷 불일치 방지
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=sr)

        chunks: list = []
        for frame in container.decode(audio=0):
            for rf in resampler.resample(frame):
                # rf.to_ndarray() shape: (1, n_samples) for planar mono
                chunks.append(rf.to_ndarray()[0].copy())  # 1D float32

        # 내부 잔여 샘플 flush
        for rf in resampler.resample(None):
            chunks.append(rf.to_ndarray()[0].copy())
    finally:
        container.close()

    if not chunks:
        return torch.zeros(1, 0, dtype=torch.float32), sr

    # numpy.concatenate → 1D → tensor (1, T) : 크기 불일치 없음
    waveform_np = np.concatenate(chunks, axis=0).astype(np.float32)

    if frame_offset > 0:
        waveform_np = waveform_np[frame_offset:]
    if num_frames > 0:
        waveform_np = waveform_np[:num_frames]

    return torch.from_numpy(waveform_np).unsqueeze(0), sr  # (1, T)


# ── 패치 5: torchaudio.info — av 기반 완전 대체 ───────────────────────────
def _av_info(path, format=None, backend=None):
    """av 기반 오디오 메타 정보 조회."""
    import av

    container = av.open(str(path))
    try:
        stream = container.streams.audio[0]
        sr = stream.sample_rate
        channels = stream.channels or 1
        if stream.duration is not None and stream.time_base is not None:
            num_frames = int(float(stream.duration * stream.time_base) * sr)
        else:
            num_frames = 0
    finally:
        container.close()

    return _AudioMetaData(
        sample_rate=sr,
        num_frames=num_frames,
        num_channels=channels,
        bits_per_sample=0,
        encoding="",
    )


torchaudio.load = _av_load
torchaudio.info = _av_info

# ═══════════════════════════════════════════════════════════════════════════
# 이하 기존 STT / 화자 분리 / 병합 로직 (변경 없음)
# ═══════════════════════════════════════════════════════════════════════════

import asyncio
import json
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

        models_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "models", "pyannote")
        )
        os.makedirs(models_dir, exist_ok=True)

        # HF 캐시 경로 설정 (오프라인 모드: 이미 다운로드된 모델 사용)
        os.environ["HF_HUB_CACHE"]          = models_dir
        os.environ["HUGGINGFACE_HUB_CACHE"] = models_dir  # legacy 호환
        os.environ["HF_HUB_OFFLINE"]        = "1"

        from pyannote.audio import Pipeline

        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token or None,
            cache_dir=models_dir,
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
                    "stage":   _state["stage"],
                    "percent": _state["percent"],
                    "running": _state["running"],
                    "error":   _state["error"],
                    "done":    _state["result"] is not None,
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"

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
