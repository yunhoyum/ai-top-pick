import base64, sys, time, requests

URL = "http://localhost:11434/v1/chat/completions"
VLM_MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemma4-e2b-2k"
THINK = len(sys.argv) > 2 and sys.argv[2] == "think"
IMAGE_PATH = "scripts/model-tests/sample_portfolio.png"

PROMPT = """이 이미지는 지원자 포트폴리오의 시스템 아키텍처 그림이다.
아래 형식으로만 한국어로 답하라.

[구성 요소]
- 이미지에 적힌 이름을 그대로 적는다. 오타도 고치지 않는다.

[묶음]
- 점선 상자마다: 상자 이름 또는 색 → 안에 있는 구성 요소

[연결]
- 화살표마다 한 줄: 출발 → 도착 (화살표 위 라벨, 없으면 생략)
- 양방향 화살표는 출발 ↔ 도착 으로 적는다.

[흐름 요약]
- 사용자 요청 흐름과 배포 흐름을 각각 2~3문장으로 설명한다."""

with open(IMAGE_PATH, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

body = {
    "model": VLM_MODEL,
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ]}],
    "temperature": 0.2,
    "max_tokens": 3000,
}
if not THINK:
    body["reasoning_effort"] = "none"   # 생각 모드 끄기

start = time.perf_counter()
r = requests.post(URL, json=body, timeout=600)
r.raise_for_status()
elapsed = time.perf_counter() - start

data = r.json()
choice = data["choices"][0]
print(f"모델: {VLM_MODEL}, 생각 모드: {'켬' if THINK else '끔'}")
print(f"{elapsed:.1f}초, 출력 {data.get('usage', {}).get('completion_tokens')}토큰")
print("종료 이유:", choice.get("finish_reason"))
print("생각 내용:", "있음" if choice["message"].get("reasoning") else "없음")
print(choice["message"]["content"])