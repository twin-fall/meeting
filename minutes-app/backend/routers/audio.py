from fastapi import APIRouter

router = APIRouter()

# TODO: 음성 처리 엔드포인트
# POST /api/audio/upload     - 음성 파일 업로드
# GET  /api/audio/devices    - 사용 가능한 마이크 목록
# POST /api/audio/record     - 실시간 녹음 시작/중지
