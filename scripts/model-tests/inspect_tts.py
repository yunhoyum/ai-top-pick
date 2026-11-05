import wave
import numpy as np
from supertonic import TTS

tts = TTS(auto_download=True)
style = tts.get_voice_style(voice_name="M1")
wav, duration = tts.synthesize("테스트 문장입니다.", voice_style=style, lang="ko")

print("배열:", type(wav), wav.dtype, wav.shape, "최소/최대:", wav.min(), wav.max())
print("rate 관련 속성:", [a for a in dir(tts) if "rate" in a.lower()])

with wave.open("scripts/model-tests/tts_0.wav", "rb") as w:
    print("저장된 wav:", w.getframerate(), "Hz,", w.getnchannels(), "채널,", w.getsampwidth() * 8, "비트")