# AI 처리 시간 전후 비교 (Playwright)

RAG 개선 1(128토큰 청크 + 문맥)과 개선 2(질문 생성 리랭커 + 상위 3개)로 실제 서비스의 AI 처리 시간이 얼마나 줄었는지 잰다.

## 무엇을 재나

| 항목 | 재는 방법 |
|---|---|
| 질문 생성 (지원자 1명) | 서류 합격 확정 → `batch_job`('면접 질문 생성') `started_at ~ finished_at` |
| 면접 중 AI 처리 (답변 1개) | Playwright가 본 WebSocket `answer_end` → 다음 `question`(또는 `interview_end`). 영상 업로드·STT 보정·채점(검색 포함)·꼬리질문 판단/생성·다음 질문 TTS가 다 들어 있다. 다음 질문이 꼬리질문인지 따로 나눈다 |

- 원본 실험 공고는 그대로 두고, 실행마다 **복제 공고**를 만든다(`clone_posting.sql`, 청크·임베딩 포함).
  - 3479: 256토큰, 문맥 없음 (지금 서비스 색인과 같음)
  - 8452: 128토큰 + Claude 문맥 (E4c)
- 지원자는 평가셋 D1~D3(`../rag-eval/document_eval_set.json`)이다. 모든 조건이 같은 지원서를 쓴다. 포트폴리오는 내용 없는 PDF다.
- 서류 보고서는 만들지 않는다. 진행 상태를 DB에서 바로 '서류 평가'로 바꾼다.
- 면접 보고서가 끝난 뒤 다음 지원자를 시작한다. LLM을 같이 쓰면 시간이 섞이기 때문이다.
- 답변은 가짜 마이크(`answer.wav`, Windows 한국어 음성)로 한다. 20초 말한 뒤 '답변 완료'를 누른다. 카메라는 Chromium 가짜 영상이라 얼굴이 없다.

## 조건

| 조건 | 원본 공고 | PC2 `pc2/.env` |
|---|---|---|
| `before` (개선 전) | 3479 | `RAG_QUESTION_RERANK=false`, `RAG_QUESTION_TOP_K=5` |
| `e1` (개선 1만) | 8452 | `RAG_QUESTION_RERANK=false`, `RAG_QUESTION_TOP_K=5` |
| `e1e2` (개선 1+2, 지금 코드 기본값) | 8452 | 두 줄을 지운다 (리랭커 켬, 상위 3) |

조건을 바꿀 때마다 PC2에서 `docker compose up -d --force-recreate ai-service`를 실행한다. ai-service 이미지는 `RAG_QUESTION_RERANK`가 들어간 코드로 한 번 재빌드해야 한다.
`QUERY_MAX_TOKENS`(검색어 분할)는 모든 조건에서 256 그대로 둔다.

## 실행 (PC1, 이 폴더에서)

```powershell
npm install                                   # 처음 한 번
powershell -ExecutionPolicy Bypass -File make_answer_wav.ps1   # answer.wav가 없을 때 한 번
node run.mjs before 3479                      # 조건마다. --applicants 3 --answer-sec 20 --headed
node run.mjs e1 8452
node run.mjs e1e2 8452
node compare.mjs before e1 e1e2
```

결과는 `results/<조건>-p<복제 공고 ID>.json`에 저장한다. 같은 조건을 여러 번 돌리면 `compare.mjs`가 합친다.
지원자 3명 기준으로 한 조건에 30~60분 걸린다.

## 구간별 시간 (ai-service 로그)

브라우저 측정에는 STT·영상 업로드·TTS가 섞여 잡음이 크다. ai-service가 면접 답변마다 아래 구간을 `구간 시간 ... step=<구간> ms=<밀리초> chunks=<청크 수>`로 남긴다.

| 구간 | 내용 |
|---|---|
| `stt_correct` | STT 보정 (LLM) |
| `answer_search` | 답변 글로 회사 문서 검색 (chunks = 찾은 청크 수) |
| `topic_wait` | 질문 주제 판정(질문 제시 때 미리 시작)을 기다린 시간 |
| `score_content` | 내용 채점 (LLM, chunks = 질문 + 답변 검색 청크 수) |
| `expression_wait` | 표정 분석을 기다린 시간 |
| `evaluate_total` | 위 전체 |
| `follow_up` | 꼬리질문 판단·생성 |
| `tts`, `question_search` | 다음 질문 음성, 질문 글로 검색 |

측정을 마치면 PC2에서 로그를 받아(`docker compose logs ai-service --no-color > ai-service-<날짜>.log`, 재빌드하면 사라지니 그 전에) 이 폴더의 `logs/`에 두고 실행한다.

```powershell
node steps.mjs logs/ai-service-<날짜>.log [조건 이름 ...]
```

## 한계

- 같은 지원서여도 LLM 출력이 매번 달라 경로(재시도·fallback·꼬리질문 여부)가 바뀐다. 표본이 작으면 차이가 우연일 수 있다. 조건마다 2번 이상 돌린다.
- 꼬리질문 생성 자체는 검색을 쓰지 않는다. 면접 중 차이는 주로 채점 검색(청크 길이 → 프롬프트 길이)에서 나온다.
- 카메라에 얼굴이 없어서 표정 분석 결과는 의미가 없다. 표정 처리 시간은 모든 조건에 똑같이 들어간다.
