"""PC2 컨테이너 -> PC1 embed/vision, PC2 Ollama 실제 모델 호출 테스트 (/health 가 아니라 모델을 실제로 쓴다)

PC2 에서 실행한다. ai-service 컨테이너와 같은 경로로 가 보려고 임시 컨테이너 안에서 돌린다.
이 파일을 PC2 의 final_project\\scripts\\model-tests\\ 로 복사한 뒤 (final_project 폴더에서):

  docker run --rm -v "${PWD}\\scripts\\model-tests:/t:ro" -e INTERNAL_TOKEN=change-me python:3.12-slim python /t/test_cross_pc.py

준비: PC1 의 storage 볼륨에 interviews/2/1.webm 이 있어야 한다 (test_vision_server.py 설명 참고).
표준 라이브러리만 쓴다 (python:3.12-slim 에는 requests 가 없다).
"""
import json
import os
import time
import urllib.error
import urllib.request

PC1 = os.environ.get("PC1_HOST", "192.168.7.106")
EMBED = f"http://{PC1}:8001/embed"
VISION = f"http://{PC1}:8002/analyze"
LLM = os.environ.get("LLM_URL", "http://host.docker.internal:11434/v1") + "/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:IQ4_XS")
TOKEN = os.environ.get("INTERNAL_TOKEN", "change-me")
VIDEO = os.environ.get("VIDEO_PATH", "interviews/2/1.webm")

failed = 0


def post(url: str, body: dict, headers: dict | None = None, timeout: int = 300):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, None, time.time() - t
    except Exception as e:  # 연결 실패, 시간 초과
        return None, str(e), time.time() - t


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    if not ok:
        failed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


H = {"X-Internal-Token": TOKEN}

# 1. PC1 embed-server: 실제 임베딩
chunks = [f"테스트 청크 {i}: 프로젝트에서 Spring Boot로 API를 개발했습니다." for i in range(32)]
status, data, sec = post(EMBED, {"texts": chunks}, H)
ok = status == 200 and data["dim"] == 1024 and len(data["vectors"]) == 32
check("PC2 -> PC1 embed (청크 32개)", ok, f"status={status} {sec:.2f}s" + (f" dim={data['dim']}" if ok else f" {data}"))

# 2. PC1 vision-server: 실제 영상 분석
status, data, sec = post(VISION, {"video_path": VIDEO, "frame_interval_sec": 1.0}, H)
ok = status == 200 and data["analyzed"] + data["skipped"] > 0
check("PC2 -> PC1 vision (영상 분석)", ok, f"status={status} {sec:.2f}s" + (f" analyzed={data['analyzed']} skipped={data['skipped']}" if ok else f" {data}"))

# 3. 토큰이 PC 사이에서도 검사된다
status, _, _ = post(EMBED, {"texts": ["a"]}, {})
check("PC2 -> PC1 embed 토큰 없음 401", status == 401, f"status={status}")

# 4. PC2 Ollama: 실제 채팅 (첫 호출은 모델을 올리느라 느릴 수 있다)
body = {
    "model": LLM_MODEL,
    "messages": [{"role": "user", "content": "백엔드 개발자 면접 질문 1개만 한 문장으로 만들어 줘."}],
    "max_tokens": 100,
    "stream": False,
}
post(LLM, {**body, "max_tokens": 1})  # 모델 로드 예열 (시간은 재지 않는다)
status, data, sec = post(LLM, body)
ok = status == 200 and bool(data["choices"][0]["message"]["content"].strip())
if ok:
    toks = data.get("usage", {}).get("completion_tokens", 0)
    print(f"       응답: {data['choices'][0]['message']['content'].strip()[:80]}")
    check("PC2 컨테이너 -> Ollama /v1/chat/completions", True, f"{sec:.2f}s {toks}토큰 {toks / sec:.1f} tok/s")
else:
    check("PC2 컨테이너 -> Ollama /v1/chat/completions", False, f"status={status} {data}")

print()
print("모두 통과" if failed == 0 else f"실패 {failed}건")
raise SystemExit(1 if failed else 0)
