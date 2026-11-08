import type { BadgeTone } from "@/components/common/Badge";

// 날짜는 서울 기준 달력 날짜로 센다 (코드베이스 4.3)
const seoulDate = (d: Date) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const dayNumber = (ymd: string) => Date.parse(`${ymd}T00:00:00Z`) / 86_400_000;

// 오늘부터 iso 날짜까지 남은 일수 (오늘이면 0)
export function daysUntil(iso: string, now = new Date()): number {
  return dayNumber(seoulDate(new Date(iso))) - dayNumber(seoulDate(now));
}

export type MilestoneBadge = { label: string; tone: BadgeTone };

function dDay(iso: string, now: Date, warnSoon: boolean): MilestoneBadge {
  const n = daysUntil(iso, now);
  // 마감이 7일 이내로 다가오면 주황으로 강조한다 (Figma: D-7 주황, D-14 남색)
  return { label: n === 0 ? "D-Day" : `D-${n}`, tone: warnSoon && n <= 7 ? "amber" : "navy" };
}

// 시작 일정의 배지: 시작 전이면 D-n, 시작했고 끝나기 전이면 '진행 중', 끝났으면 '완료'
export function startBadge(startIso: string | null, endIso: string | null, now = new Date()): MilestoneBadge | null {
  if (!startIso) return null;
  if (now < new Date(startIso)) return dDay(startIso, now, false);
  if (endIso && now >= new Date(endIso)) return { label: "완료", tone: "gray" };
  return { label: "진행 중", tone: "gray" };
}

// 마감 일정의 배지: 마감 전이면 D-n, 지났으면 '마감'
export function endBadge(endIso: string | null, now = new Date()): MilestoneBadge | null {
  if (!endIso) return null;
  if (now >= new Date(endIso)) return { label: "마감", tone: "gray" };
  return dDay(endIso, now, true);
}
