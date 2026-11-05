import time
from supertonic import TTS
import numpy as np

tts = TTS(auto_download=True)
style = tts.get_voice_style(voice_name="M1")

texts = [
    "안녕하세요. 지금부터 면접을 시작하겠습니다.",
    "최근에 참여한 백엔드 프로젝트에서 직면했던 기술적 문제와 해결 방법을 설명해 주세요.",
]

# 예열 (첫 실행 지연 제외)
tts.synthesize(texts[0], voice_style=style, lang="ko")

for i, text in enumerate(texts):
    start = time.perf_counter()
    wav, duration = tts.synthesize(text, voice_style=style, lang="ko")
    elapsed = time.perf_counter() - start
    tts.save_audio(wav, f"scripts/model-tests/tts_{i}.wav")
    dur = float(np.ravel(duration)[0])
    print(f"[{i}] 합성 {elapsed:.2f}초, 음성 길이 {dur:.2f}초, duration 모양 {np.shape(duration)}")