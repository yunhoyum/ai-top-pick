import base64, sys, time, threading, requests

URL = "http://localhost:11434/v1/chat/completions"
TEXT_MODEL = "exaone3.5:2.4b"
VLM_MODEL = "gemma4:e2b-it-qat"
IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else "scripts/model-tests/sample_portfolio.png"

def call(model, messages):
    start = time.perf_counter()
    r = requests.post(URL, json={
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }, timeout=600)
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return text, time.perf_counter() - start

def text_msg():
    return [{"role": "user", "content": "백엔드 개발자 면접 질문 3개를 만들어줘."}]

def image_msg():
    with open(IMAGE_PATH, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return [{"role": "user", "content": [
        {"type": "text", "text": "이 포트폴리오 이미지의 글자를 옮겨 적고, 도식이 있으면 무엇을 나타내는지 한국어로 설명해줘."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}]

# 1) 단독 실행: 기준 시간
for name, model, msgs in [("text", TEXT_MODEL, text_msg()),
                          ("vlm", VLM_MODEL, image_msg())]:
    call(model, msgs)          # 예열 (모델 로드 시간 제외용)
    _, t = call(model, msgs)
    print(f"[단독 {name}] {t:.1f}초")

print(">>> 다른 창에서 ollama ps 로 두 모델이 모두 있는지 확인하세요")
input("확인했으면 Enter...")

# 2) 동시 실행
results = {}
def worker(name, model, msgs):
    results[name] = call(model, msgs)

threads = [
    threading.Thread(target=worker, args=("text", TEXT_MODEL, text_msg())),
    threading.Thread(target=worker, args=("vlm", VLM_MODEL, image_msg())),
]
for th in threads:
    th.start()
for th in threads:
    th.join()

for name, (out, t) in results.items():
    print(f"[동시 {name}] {t:.1f}초")
    print(out[:300])
    print("-" * 40)