// 일시는 서버에 시간대(+09:00)를 붙여 보내고, 화면에는 Asia/Seoul 기준으로 보여준다 (코드베이스 4.3)

// <input type="datetime-local"> 값("2026-10-27T10:00") → 서버로 보낼 ISO 문자열
export const toIso = (local: string) => `${local}:00+09:00`;

// 서버가 준 ISO 문자열 → <input type="datetime-local"> 값 (Asia/Seoul)
export function toInputValue(iso: string | null): string {
  if (!iso) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}

// "2026-10-27T10:00" → "2026.10.27"
const toDotDate = (local: string) => local.slice(0, 10).replaceAll("-", ".");

// 전체 채용 기간: 서류 접수 시작 ~ 면접 합격자 발표 (ADM-004)
export function formatPeriod(startLocal: string, endLocal: string): string | null {
  if (!startLocal || !endLocal) return null;
  return `${toDotDate(startLocal)} ~ ${toDotDate(endLocal)}`;
}

// 파일 크기 표시 (예: 2.1 MB)
export function formatFileSize(bytes: number | null): string {
  if (bytes == null) return "";
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
