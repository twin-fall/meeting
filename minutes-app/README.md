# 회의록 자동작성 앱

인사팀을 위한 AI 기반 회의록 자동 생성 데스크탑 앱. 음성/텍스트 처리는 로컬에서 수행하고, LLM 호출만 외부 API를 사용합니다.

## 설치 순서

1. **저장소 클론 및 Node 패키지 설치**
   ```bash
   git clone <repo-url>
   cd minutes-app
   npm install
   ```

2. **Python 패키지 설치**
   ```bash
   pip install -r backend/requirements.txt
   ```

3. **AI 모델 다운로드** ← 최초 1회, 약 2GB, 시간 소요
   ```bash
   python setup.py
   ```
   > HuggingFace 토큰이 필요합니다. 실행 시 입력하라는 안내가 나옵니다.
   > 토큰 발급: https://huggingface.co/settings/tokens

4. **앱 실행**
   ```bash
   npm start
   ```

## 주의사항

- `models/` 폴더는 Git에 포함되지 않으므로, 클론 후 반드시 `python setup.py`를 실행해야 합니다.
- `pyannote` 화자 분리 모델은 HuggingFace 라이선스 동의가 필요합니다: https://huggingface.co/pyannote/speaker-diarization-3.1
- API 키는 이 기기의 로컬 스토리지에만 저장되며 외부로 전송되지 않습니다.
