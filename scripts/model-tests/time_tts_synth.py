import os, time
from supertonic import TTS

tts = TTS(model_dir=os.environ.get("TTS_MODEL_DIR"), auto_download=False)
style = tts.get_voice_style(voice_name="M1")
text = "최근에 참여한 백엔드 프로젝트에서 직면했던 기술적 문제와 해결 방법을 설명해 주세요."

tts.synthesize(text, voice_style=style, lang="ko")   # 예열
for _ in range(3):
    s = time.perf_counter()
    tts.synthesize(text, voice_style=style, lang="ko")
    print(f"합성 {time.perf_counter() - s:.2f}초")