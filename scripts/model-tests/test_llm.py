# test_llm.py  (pip install requests)
import json, time, requests

URL = "http://localhost:11434/v1/chat/completions"
MODEL = "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:IQ4_XS"

def chat(prompt):
    start = time.perf_counter()
    r = requests.post(URL, json={
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }, timeout=300)
    r.raise_for_status()
    elapsed = time.perf_counter() - start
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    tokens = data.get("usage", {}).get("completion_tokens")
    return text, elapsed, tokens

# 0) 예열: 첫 호출은 모델 로드 시간이 섞인다
chat("안녕")

# 1) 한국어 품질과 속도
text, t, n = chat("백엔드 개발자 지원자에게 할 기술 면접 질문 3개를 만들어줘.")
print(text)
print(f"{t:.1f}초, {n}토큰, {n / t:.1f} tok/s" if n else f"{t:.1f}초")

# 2) JSON 형식 준수율
PROMPT = """백엔드 개발자 면접 질문 3개를 만들어라.
다른 말 없이 아래 JSON만 출력하라.
{"questions": [{"question": "...", "intent": "..."}]}"""

N, ok = 10, 0
for i in range(N):
    text, _, _ = chat(PROMPT)
    s = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        obj = json.loads(s)
        assert len(obj["questions"]) == 3
        ok += 1
    except Exception:
        print(f"[{i}] 실패: {text[:80]}")
print(f"JSON 성공 {ok}/{N}")