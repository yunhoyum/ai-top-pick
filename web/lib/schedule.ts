// 전형별 일정 순서 검사 (ADM-004). 서버 규칙(main-api/app/domain/rules.py)과 같은 순서이며,
// 입력하는 동안 바로 보여 주려고 화면에서도 검사한다. 최종 판단은 서버가 한다.
// datetime-local 값("2026-11-10T09:00")은 문자열 비교가 곧 시간 순서 비교다.

export type ScheduleKey =
  | "doc_start_at"
  | "doc_end_at"
  | "doc_result_at"
  | "interview_start_at"
  | "interview_end_at"
  | "interview_result_at";

export type ScheduleErrors = Partial<Record<ScheduleKey, string>>;

// 서류 시작 ≤ 서류 마감 < 서류 발표 < 면접 시작 ≤ 면접 마감 < 면접 발표
export function validateSchedule(v: Record<ScheduleKey, string>): ScheduleErrors {
  const errors: ScheduleErrors = {};
  // 앞 값이 뒤 값보다 늦으면(같은 시각을 허용하지 않을 때는 같아도) 어긋난 것이다. 비어 있으면 비교하지 않는다
  const wrong = (before: ScheduleKey, after: ScheduleKey, allowEqual: boolean) =>
    !!v[before] && !!v[after] && (allowEqual ? v[before] > v[after] : v[before] >= v[after]);

  if (wrong("doc_start_at", "doc_end_at", true)) {
    errors.doc_end_at = "서류 접수 마감은 서류 접수 시작과 같거나 이후여야 합니다.";
  }
  if (wrong("doc_end_at", "doc_result_at", false) || wrong("doc_result_at", "interview_start_at", false)) {
    errors.doc_result_at = "서류 합격자 발표는 서류 접수 마감과 면접 시작 사이여야 합니다.";
  }
  // 서류 합격자 발표가 비어 있어도 면접은 서류 접수 마감 뒤에 시작해야 한다 (서류 전형 다음에 면접 전형)
  if (!v.doc_result_at && wrong("doc_end_at", "interview_start_at", false)) {
    errors.interview_start_at = "면접 시작은 서류 접수 마감 이후여야 합니다.";
  }
  if (wrong("interview_start_at", "interview_end_at", true)) {
    errors.interview_end_at = "면접 마감은 면접 시작과 같거나 이후여야 합니다.";
  }
  if (wrong("interview_end_at", "interview_result_at", false)) {
    errors.interview_result_at = "면접 합격자 발표는 면접 마감 이후여야 합니다.";
  }
  return errors;
}
