"""RAG 개선 2-② LLM 청크 필터 평가. ai-service 이미지에서 실행한다 (PC2, EXAONE).

results/rerank-candidates-E4c.json(검색어마다 벡터 검색 상위 8개)을 검색어마다 한 번에 보여 주고,
질문 근거로 쓸 수 있는 문서 번호를 고르게 한다. 순서는 검색 순위 그대로다 (실제 그래프에 넣을 때와 같게).
결과: results/filter-E4c-<실험 ID>.json. 정답(사람 관련도)과의 비교는 run_rerank_eval.py compare가 한다.

DB·embed-server는 쓰지 않는다. PC2의 final_project 폴더에서 (PowerShell):
  docker run --rm --env-file pc2/.env -v "${PWD}/ai-service:/src" -v "${PWD}/scripts/rag-eval:/eval" -w /src pc2-ai-service:latest python /eval/run_chunk_filter_eval.py exaone
"""

import json
import sys
import time
from pathlib import Path

sys.path[:0] = ["/src"]

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.chains.structured import invoke_structured
from app.core.config import get_settings
from app.core.llm import get_chat_model
from app.prompts.question import SYSTEM

RESULTS = Path("/eval/results")


class ChunkPick(BaseModel):
    relevant: list[int]


def prompt(query: str, chunks: list[str]):
    docs = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(chunks, 1))
    return [
        SystemMessage(content=SYSTEM),
        HumanMessage(
            content=f"""[지원자 서류]
{query}

[회사 프로젝트 문서]
{docs}

지원자 서류의 경험으로 면접 질문을 만들 때 근거로 쓸 수 있는 회사 프로젝트 문서의 번호를 모두 골라 JSON으로 출력하라.
- 지원자 서류에 나온 기술, 다룬 문제, 쓴 방법과 같은 주제를 다루는 문서만 고른다.
- 단어만 같고 다루는 내용이 다르면 고르지 않는다.
- 해당하는 문서가 없으면 빈 목록을 출력한다.

형식: {{"relevant": [1, 3]}}"""
        ),
    ]


def main(label: str):
    data = json.loads((RESULTS / "rerank-candidates-E4c.json").read_text(encoding="utf-8"))
    model, out = get_chat_model(), []
    for q in data["queries"]:
        cands = q["candidates"]
        start = time.perf_counter()
        try:
            picked = invoke_structured(model, prompt(q["query"], [c["content"] for c in cands]), ChunkPick).relevant
            error = None
        except Exception as e:
            picked, error = [], str(e)
        seconds = round(time.perf_counter() - start, 1)
        kept = [cands[i - 1]["chunk_id"] for i in dict.fromkeys(picked) if 1 <= i <= len(cands)]
        out.append({"key": q["key"], "picked": picked, "kept": kept, "seconds": seconds, "error": error})
        print(q["key"], picked, f"{seconds}s", error or "")
    path = RESULTS / f"filter-E4c-{label}.json"
    path.write_text(json.dumps({"model": get_settings().LLM_MODEL, "results": out}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("저장:", path)


if __name__ == "__main__":
    main(sys.argv[1])
