// 서류 전형 평가 화면 표시 규칙 (화면 17, 18)

// 순위 표 머리글의 짧은 항목 이름 (Figma: '기술 사례 30')
const SHORT_NAMES: Record<string, string> = { "기술 적용 사례": "기술 사례" };
export const shortCriteriaName = (name: string) => SHORT_NAMES[name] ?? name;

// 항목 점수 × 비율: 정수면 정수로, 아니면 소수 첫째 자리까지 (Figma: '28', '13.5')
export const formatWeighted = (value: string) => String(Number(value));

// 총점·평균: 소수 첫째 자리까지 (Figma: '89.0')
export const formatTotal = (value: string) => Number(value).toFixed(1);

// 보고서가 아직 없는 지원자의 '결과 보고서' 칸 (서류 보고서 작업 상태)
const REPORT_STATUS_LABELS: Record<string, string> = {
  대기: "생성 대기",
  "실행 중": "생성 중",
  실패: "생성 실패",
  없음: "보고서 없음",
};
export const reportStatusLabel = (status: string) => REPORT_STATUS_LABELS[status] ?? status;

// 상위 비율: 2위 / 72명 → 상위 3% (올림)
export const topPercent = (rank: number, count: number) => Math.ceil((rank / count) * 100);
