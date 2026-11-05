import os
import time

import requests

URL = "http://127.0.0.1:8001"
H = {"X-Internal-Token": os.environ.get("INTERNAL_TOKEN", "change-me")}


def embed(texts):
    return requests.post(f"{URL}/embed", json={"texts": texts}, headers=H)


print("health:", requests.get(f"{URL}/health").json())

r = embed(["안녕하세요"]).json()
print("dim:", r["dim"], "| 벡터 수:", len(r["vectors"]))

a, b, c = embed(["저는 백엔드 개발자를 지망합니다.", "서버 개발자가 되고 싶습니다.", "오늘 점심은 김치찌개를 먹었다."]).json()["vectors"]
dot = lambda x, y: sum(p * q for p, q in zip(x, y))
print(f"유사 문장: {dot(a, b):.3f} | 무관 문장: {dot(a, c):.3f} | 통과: {dot(a, b) > dot(a, c)}")

chunks = [f"테스트 청크 {i}: 프로젝트에서 Spring Boot로 API를 개발했습니다." for i in range(32)]
t = time.time()
embed(chunks)
print(f"청크 32개: {time.time() - t:.2f}초")

print("토큰 없음:", requests.post(f"{URL}/embed", json={"texts": ["a"]}).status_code, "(401 기대)")
print("빈 목록:", embed([]).status_code, "(422 기대)")
print("공백 문장:", embed(["   "]).status_code, "(422 기대)")
