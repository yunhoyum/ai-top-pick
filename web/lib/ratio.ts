// 평가 항목 비율 입력(화면 06, 07)의 합계 계산. values의 빈 문자열은 아직 입력하지 않은 항목이다

export type RatioSummary = {
  sum: number;
  blanks: number;
  // 모두 입력했고 합이 정확히 100이며 오류가 없다
  complete: boolean;
};

export function summarizeRatios(
  criteria: { criteria_id: number }[],
  values: Record<number, string>,
  hasItemError: boolean,
): RatioSummary {
  const value = (id: number) => values[id] ?? "";
  const sum = criteria.reduce((total, c) => total + (value(c.criteria_id) ? Number(value(c.criteria_id)) : 0), 0);
  const blanks = criteria.filter((c) => value(c.criteria_id) === "").length;
  return { sum, blanks, complete: sum === 100 && blanks === 0 && !hasItemError };
}
