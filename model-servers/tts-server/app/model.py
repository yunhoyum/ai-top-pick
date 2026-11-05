import io
import os
import threading
import wave

import numpy as np
from supertonic import TTS

MODEL_DIR = os.getenv("TTS_MODEL_DIR")  # 없으면 라이브러리 기본 위치
AUTO_DOWNLOAD = os.getenv("TTS_AUTO_DOWNLOAD", "1") == "1"
VOICE = os.getenv("TTS_VOICE", "M1")
LANG = os.getenv("TTS_LANG", "ko")
SAMPLE_RATE = int(os.environ["TTS_SAMPLE_RATE"])  # 0번에서 확인한 값


def to_wav_bytes(wav) -> bytes:
    """실수 배열(-1~1)을 16비트 모노 wav 바이트로 바꾼다."""
    samples = np.ravel(np.asarray(wav, dtype=np.float32))
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class TTSModel:
    def __init__(self):
        self._tts = None
        self._style = None
        self._lock = threading.Lock()

    def load(self):
        self._tts = TTS(model_dir=MODEL_DIR, auto_download=AUTO_DOWNLOAD)
        self._style = self._tts.get_voice_style(voice_name=VOICE)
        self.synthesize("준비")  # 예열

    def synthesize(self, text: str) -> bytes:
        with self._lock:
            wav, _ = self._tts.synthesize(text, voice_style=self._style, lang=LANG)
        return to_wav_bytes(wav)


tts_model = TTSModel()