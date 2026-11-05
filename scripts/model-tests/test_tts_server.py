from pathlib import Path

import requests
import os

URL = "http://localhost:8003"
H = {"X-Internal-Token": os.environ.get("INTERNAL_TOKEN", "change-me")}
# 실행 위치와 상관없이 이 스크립트가 있는 폴더에 저장
OUT = Path(__file__).resolve().parent / "tts_server_out.wav"

print("health:", requests.get(f"{URL}/health").json())

r = requests.post(f"{URL}/tts", json={"text": "자기소개를 해 주세요."}, headers=H)
print("정상:", r.status_code, r.headers.get("content-type"), len(r.content), "바이트")
OUT.write_bytes(r.content)
print("저장:", OUT)

print("토큰 없음:", requests.post(f"{URL}/tts", json={"text": "테스트"}).status_code)          # 401 기대
print("빈 텍스트:", requests.post(f"{URL}/tts", json={"text": "   "}, headers=H).status_code)   # 422 기대
