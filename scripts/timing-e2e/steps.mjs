// ai-service '구간 시간' 로그를 results/*.json의 질문(question_id)과 맞춰 조건·질문 종류·구간별로 모은다.
// PC2에서 로그를 파일로 받아 이 폴더의 logs/에 둔다:  docker compose logs ai-service --no-color > ai-service-<날짜>.log
// 사용: node steps.mjs logs/ai-service-<날짜>.log [조건 이름 ...]
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIR = join(dirname(fileURLToPath(import.meta.url)), "results");
const [logFile, ...only] = process.argv.slice(2);
if (!logFile) {
  console.error("사용: node steps.mjs <ai-service 로그 파일> [조건 이름 ...]");
  process.exit(1);
}

// question_id → {label, kind}. 다음 질문으로 처음 나온 꼬리질문도 넣는다
const owner = new Map();
const labels = [];
for (const f of readdirSync(DIR).filter((f) => f.endsWith(".json"))) {
  const r = JSON.parse(readFileSync(join(DIR, f), "utf8"));
  if (only.length && !only.includes(r.label)) continue;
  if (!labels.includes(r.label)) labels.push(r.label);
  for (const t of r.interviews.flatMap((i) => i.transitions)) {
    owner.set(String(t.question_id), { label: r.label, kind: t.kind });
    if (typeof t.next === "number") owner.set(String(t.next), { label: r.label, kind: t.next_kind });
  }
}

const LINE = /구간 시간 session=\S+ question_id=(\S+) qkey=\S+ step=(\S+) ms=(\d+) chunks=(\S+)/;
const data = {}; // label → kind → step → {ms: [], chunks: []}
for (const line of readFileSync(logFile, "utf8").split("\n")) {
  const m = line.match(LINE);
  const who = m && owner.get(m[1]);
  if (!who) continue;
  const cell = (((data[who.label] ??= {})[who.kind] ??= {})[m[2]] ??= { ms: [], chunks: [] });
  cell.ms.push(Number(m[3]) / 1000);
  if (m[4] !== "None") cell.chunks.push(Number(m[4]));
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
const STEPS = ["stt_correct", "answer_search", "topic_wait", "score_content", "expression_wait", "evaluate_total",
               "follow_up", "tts", "question_search"];
for (const label of labels.filter((l) => data[l])) {
  console.log(`\n[${label}]`);
  for (const [kind, steps] of Object.entries(data[label])) {
    const parts = STEPS.filter((s) => steps[s]).map((s) => {
      const c = steps[s];
      const chunks = c.chunks.length ? ` 청크${mean(c.chunks).toFixed(1)}` : "";
      return `${s} ${mean(c.ms).toFixed(2)}초(n${c.ms.length}${chunks})`;
    });
    console.log(`  ${kind}: ${parts.join(" | ")}`);
  }
}
