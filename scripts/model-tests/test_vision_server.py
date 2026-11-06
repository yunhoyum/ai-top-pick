"""vision-server API 테스트 (PC1, 127.0.0.1:8002)

사전 준비: 테스트 영상이 storage 볼륨의 VIDEO_PATH 에 있어야 한다.
  녹화: scripts/model-tests/record_webm.html 로 test_face.webm 을 만든다 (얼굴이 나왔다 사라지게)
  복사 (final_project 폴더에서, Git Bash 기준):
    MSYS_NO_PATHCONV=1 docker run --rm -v pc1_storage:/data/storage \
      -v "$(pwd -W)/scripts/model-tests/test_face.webm:/src.webm:ro" \
      --entrypoint sh pc1-vision-server -c \
      "mkdir -p /data/storage/interviews/2 && cp /src.webm /data/storage/interviews/2/1.webm"
실행: python scripts/model-tests/test_vision_server.py   (한글이 깨지면 PYTHONIOENCODING=utf-8)
"""
import os
import sys
import time

import requests

URL = "http://127.0.0.1:8002"
TOKEN = os.environ.get("INTERNAL_TOKEN", "change-me")
H = {"X-Internal-Token": TOKEN}
VIDEO_PATH = os.environ.get("VIDEO_PATH", "interviews/2/1.webm")
EMOTIONS = {"angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"}

failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    if not ok:
        failed += 1
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def analyze(path: str, interval: float = 1.0, headers=H) -> requests.Response:
    return requests.post(
        f"{URL}/analyze",
        json={"video_path": path, "frame_interval_sec": interval},
        headers=headers,
        timeout=300,
    )


check("health", requests.get(f"{URL}/health").json() == {"status": "ok"})

# --- 정상 분석 ---
start = time.time()
r = analyze(VIDEO_PATH)
elapsed = time.time() - start
check("분석 200", r.status_code == 200, f"(status {r.status_code})")
if r.status_code != 200:
    print(r.text[:300])
    print("영상이 볼륨에 있는지 확인하세요 (파일 상단 설명 참고)")
    sys.exit(1)

d = r.json()
frames = d["frames"]
print(f"       처리 시간 {elapsed:.2f}초 | analyzed {d['analyzed']} | skipped {d['skipped']}")
check("analyzed == len(frames)", d["analyzed"] == len(frames))
check("얼굴 있는 프레임이 1개 이상", d["analyzed"] > 0)
check("얼굴 없는 프레임은 skipped 로 센다 (영상에서 얼굴이 사라졌다면 > 0)", d["skipped"] > 0, f"(skipped {d['skipped']})")
ts = [f["t"] for f in frames]
check("t 가 증가 순서", ts == sorted(ts))
check("프레임 간격이 대체로 1초", all(0.9 <= b - a for a, b in zip(ts, ts[1:])))
check("감정 7가지 키", all(set(f["scores"]) == EMOTIONS for f in frames))
check("scores 합이 1.0 (0~1 비율)", all(abs(sum(f["scores"].values()) - 1.0) < 0.01 for f in frames))
check("emotion 이 최고 점수 감정", all(f["emotion"] == max(f["scores"], key=f["scores"].get) for f in frames))

# 얼굴이 사라진 구간은 t 가 건너뛴다
gaps = [(a, b) for a, b in zip(ts, ts[1:]) if b - a > 2.0]
print(f"       얼굴 없는 구간(t 가 건너뛴 곳): {gaps}")

counts: dict[str, int] = {}
for f in frames:
    counts[f["emotion"]] = counts.get(f["emotion"], 0) + 1
print(f"       감정 분포: {counts}")

# --- 오류 처리 ---
check("토큰 없음 401", analyze(VIDEO_PATH, headers={}).status_code == 401)
check("틀린 토큰 401", analyze(VIDEO_PATH, headers={"X-Internal-Token": "wrong"}).status_code == 401)
check("없는 파일 404", analyze("interviews/9/none.webm").status_code == 404)
check("루트 밖 경로(../) 400", analyze("../etc/passwd").status_code == 400)
check("절대경로 400", analyze("/etc/passwd").status_code == 400)
check("interval 너무 작음 422", analyze(VIDEO_PATH, 0.01).status_code == 422)
check("interval 너무 큼 422", analyze(VIDEO_PATH, 99).status_code == 422)

print()
print("모두 통과" if failed == 0 else f"실패 {failed}건")
sys.exit(1 if failed else 0)
