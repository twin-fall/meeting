"""
setup.py - AI 모델 최초 1회 다운로드 스크립트

실행: python setup.py
소요 시간: 인터넷 속도에 따라 약 10~30분 (총 약 2GB)
"""

import os
import sys

# tqdm 설치 여부 확인
try:
    from tqdm import tqdm
except ImportError:
    print("tqdm을 설치합니다...")
    os.system(f"{sys.executable} -m pip install tqdm")
    from tqdm import tqdm

MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")


def make_dirs():
    """models/ 하위 폴더 생성"""
    for sub in ("whisper", "pyannote", "klue-bert"):
        path = os.path.join(MODELS_DIR, sub)
        os.makedirs(path, exist_ok=True)
    print("✅ models/ 폴더 구조 생성 완료")


def download_whisper():
    """faster-whisper medium 모델 다운로드 (~500MB)"""
    print("\n[1/3] faster-whisper medium 모델 다운로드 중...")
    try:
        from faster_whisper import WhisperModel
        dest = os.path.join(MODELS_DIR, "whisper")
        # download_root 지정 시 해당 경로에 캐시됨
        WhisperModel("medium", device="cpu", compute_type="int8", download_root=dest)
        print("✅ Whisper 모델 다운로드 완료")
    except ImportError:
        print("⚠️  faster-whisper가 설치되지 않았습니다. 먼저 pip install -r backend/requirements.txt 를 실행하세요.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Whisper 모델 다운로드 실패: {e}")
        sys.exit(1)


def download_pyannote(hf_token: str):
    """pyannote/speaker-diarization-3.1 다운로드 (~1GB)"""
    print("\n[2/3] pyannote 화자 분리 모델 다운로드 중 (약 1GB)...")
    try:
        from pyannote.audio import Pipeline
        dest = os.path.join(MODELS_DIR, "pyannote")
        os.environ["PYANNOTE_CACHE"] = dest
        Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        print("✅ pyannote 모델 다운로드 완료")
    except ImportError:
        print("⚠️  pyannote.audio가 설치되지 않았습니다. 먼저 pip install -r backend/requirements.txt 를 실행하세요.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ pyannote 모델 다운로드 실패: {e}")
        print("   HuggingFace 토큰이 올바른지, 그리고 아래 페이지에서 모델 라이선스에 동의했는지 확인하세요:")
        print("   https://huggingface.co/pyannote/speaker-diarization-3.1")
        sys.exit(1)


def download_klue_bert():
    """klue/bert-base 기반 NER 모델 다운로드 (~400MB)"""
    print("\n[3/3] KLUE BERT NER 모델 다운로드 중 (약 400MB)...")
    try:
        from transformers import AutoTokenizer, AutoModelForTokenClassification
        dest = os.path.join(MODELS_DIR, "klue-bert")
        AutoTokenizer.from_pretrained("klue/bert-base", cache_dir=dest)
        AutoModelForTokenClassification.from_pretrained("klue/bert-base", cache_dir=dest)
        print("✅ KLUE BERT 모델 다운로드 완료")
    except ImportError:
        print("⚠️  transformers가 설치되지 않았습니다. 먼저 pip install -r backend/requirements.txt 를 실행하세요.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ KLUE BERT 모델 다운로드 실패: {e}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("  회의록 자동작성 앱 - 모델 설치 스크립트")
    print("  총 약 2GB 다운로드 · 인터넷 속도에 따라 시간 소요")
    print("=" * 60)

    # HuggingFace 토큰 입력
    print("\npyannote 화자 분리 모델은 HuggingFace 토큰이 필요합니다.")
    print("토큰 발급: https://huggingface.co/settings/tokens")
    print("모델 라이선스 동의: https://huggingface.co/pyannote/speaker-diarization-3.1\n")
    hf_token = input("HuggingFace 토큰을 입력하세요 (없으면 Enter로 건너뜀): ").strip()

    make_dirs()
    download_whisper()

    if hf_token:
        download_pyannote(hf_token)
    else:
        print("\n⚠️  HuggingFace 토큰 미입력 - pyannote 모델 건너뜀")
        print("   화자 분리 기능을 사용하려면 나중에 토큰을 입력하고 다시 실행하세요.")

    download_klue_bert()

    print("\n" + "=" * 60)
    print("  설치가 완료되었습니다. 앱을 실행하세요.")
    print("  실행 명령: npm start")
    print("=" * 60)


if __name__ == "__main__":
    main()
