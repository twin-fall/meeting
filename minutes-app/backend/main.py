from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers import api_key, employee, audio, transcribe, minutes, stt

app = FastAPI(title="회의록 자동작성 API", version="1.0.0")

# Electron 로컬 프론트엔드에서의 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 로컬 전용 앱이므로 전체 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(api_key.router, prefix="/api/key", tags=["API 키"])
app.include_router(employee.router, prefix="/api/employee", tags=["사원명부"])
app.include_router(audio.router, prefix="/api/audio", tags=["음성"])
app.include_router(transcribe.router, prefix="/api/transcribe", tags=["음성인식"])
app.include_router(minutes.router, prefix="/api/minutes", tags=["회의록"])
app.include_router(stt.router, prefix="/stt", tags=["STT"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8765, reload=False)
