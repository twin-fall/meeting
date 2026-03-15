from fastapi import APIRouter

router = APIRouter()

# TODO: 음성 인식 및 화자 분리 엔드포인트
# POST /api/transcribe/run   - faster-whisper STT + pyannote 화자 분리
# GET  /api/transcribe/status - 처리 상태 조회 (진행률)
