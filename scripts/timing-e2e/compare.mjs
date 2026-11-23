// results/*.json을 조건별로 모아 시간을 비교한다.  사용: node compare.mjs [조건 이름 ...] (순서대로 표시, 없으면 전부)
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIR = join(dirname(fileURLToPath(import.meta.url)), "results");
const runs = readdirSync(DIR).filter((f) => f.endsWith(".json")).map((f) => JSON.parse(readFileSync(join(DIR, f), "utf8")));
const labels = process.argv.slice(2).length ? process.argv.slice(2) : [...new Set(runs.map((r) => r.label))];

const stats = (xs) => {
  if (!xs.length) return "-";
  const s = [...xs].sort((a, b) => a - b);
  const mean = s.reduce((a, b) => a + b, 0) / s.length;
  const median = s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2;
  return `n=${s.length} 평균 ${mean.toFixed(1)} 중앙 ${median.toFixed(1)} (${s[0].toFixed(1)}~${s.at(-1).toFixed(1)})`;
};

const table = [];
for (const label of labels) {
  const mine = runs.filter((r) => r.label === label);
  const jobs = mine.flatMap((r) => r.question_jobs.filter((j) => j.status === "완료"));
  const trans = mine.flatMap((r) => r.interviews.flatMap((i) => i.transitions)).filter((t) => t.seconds != null);
  table.push({
    조건: label,
    "원본 공고": [...new Set(mine.map((r) => r.source_posting_id))].join(","),
    "질문 생성(지원자당, 초)": stats(jobs.map((j) => j.seconds)),
    "질문 생성(AI 질문 1개당, 초)": stats(jobs.map((j) => j.seconds / Math.max(1, j.ai_questions))),
    "답변→다음 질문 전체(초)": stats(trans.map((t) => t.seconds)),
    "답변→꼬리질문(초)": stats(trans.filter((t) => t.next_kind === "꼬리질문").map((t) => t.seconds)),
    "답변→기본 질문·종료(초)": stats(trans.filter((t) => t.next_kind !== "꼬리질문").map((t) => t.seconds)),
    "꼬리질문 수": trans.filter((t) => t.next_kind === "꼬리질문").length,
  });
}
for (const row of table) {
  console.log(`\n[${row.조건}]`);
  for (const [k, v] of Object.entries(row)) if (k !== "조건") console.log(`  ${k}: ${v}`);
}
