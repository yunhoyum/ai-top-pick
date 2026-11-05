import requests

URL = "http://localhost:8003"
H = {"X-Internal-Token": "dev-token"}

print("health:", requests.get(f"{URL}/health").json())

r = requests.post(f"{URL}/tts", json={"text": "자기소개를 해 주세요."}, headers=H)
print("정상:", r.status_code, r.headers.get("content-type"), len(r.content), "바이트")
with open("scripts/model-tests/tts_server_out.wav", "wb") as f:
    f.write(r.content)

print("토큰 없음:", requests.post(f"{URL}/tts", json={"text": "테스트"}).status_code)          # 401 기대
print("빈 텍스트:", requests.post(f"{URL}/tts", json={"text": "   "}, headers=H).status_code)   # 422 기대