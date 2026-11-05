import os, threading, time, requests

LLM_URL = "http://127.0.0.1:11434/v1/chat/completions"
LLM_MODEL = "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:IQ4_XS"
TTS_URL = "http://127.0.0.1:8003/tts"
H = {"X-Internal-Token": os.environ.get("INTERNAL_TOKEN", "change-me")}
TTS_TEXT = "최근에 참여한 백엔드 프로젝트에서 직면했던 기술적 문제와 해결 방법을 설명해 주세요."

def llm_call():
    start = time.perf_counter()
    r = requests.post(LLM_URL, json={
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "백엔드 개발자 면접 질문 3개를 만들어줘."}],
        "temperature": 0.2,
        "max_tokens": 400,
    }, timeout=300)
    r.raise_for_status()
    t = time.perf_counter() - start
    n = r.json().get("usage", {}).get("completion_tokens") or 0
    return t, n

def tts_call():
    start = time.perf_counter()
    r = requests.post(TTS_URL, json={"text": TTS_TEXT}, headers=H, timeout=60)
    r.raise_for_status()
    return time.perf_counter() - start

def avg(xs):
    return sum(xs) / len(xs)

# 0) 예열
llm_call()
tts_call()

# 1) 단독 3회씩
llm_alone = [llm_call() for _ in range(3)]
tts_alone = [tts_call() for _ in range(3)]

# 2) LLM 생성 중 TTS 3회
llm_during, tts_during = [], []
for _ in range(3):
    res = {}
    th = threading.Thread(target=lambda: res.update(llm=llm_call()))
    th.start()
    time.sleep(1)                 # LLM이 생성을 시작한 뒤 TTS 요청
    tts_during.append(tts_call())
    th.join()
    llm_during.append(res["llm"])

print(f"LLM 단독: {avg([n / t for t, n in llm_alone]):.1f} tok/s")
print(f"LLM 동시: {avg([n / t for t, n in llm_during]):.1f} tok/s")
print(f"TTS 단독: {avg(tts_alone):.2f}초")
print(f"TTS 동시: {avg(tts_during):.2f}초")