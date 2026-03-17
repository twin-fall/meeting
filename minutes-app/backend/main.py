import sys
import os

# 스크립트 실행 방식(python main.py)과 모듈 실행 방식 모두에서
# routers/ 패키지를 안정적으로 찾을 수 있도록 경로를 명시적으로 추가한다.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from routers import api_key, employee, audio, transcribe, minutes, stt, pseudonymize, llm, output

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
app.include_router(pseudonymize.router, prefix="/pseudonymize", tags=["가명처리"])
app.include_router(llm.router,            prefix="/llm",     tags=["LLM"])
app.include_router(output.router,         prefix="/output",  tags=["출력"])
app.include_router(output.session_router, prefix="/session", tags=["세션"])


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    # 문자열 "main:app" 대신 app 객체를 직접 전달한다.
    # 문자열 방식은 uvicorn이 모듈을 재임포트할 때 sys.path 상태에 따라
    # 실패할 수 있다.
    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
