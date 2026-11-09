import styles from "./Pagination.module.css";

const GROUP = 5; // 쪽 번호는 1~5, 6~10처럼 5개씩 묶어서 보여 준다

// 쪽 이동. 쪽이 하나뿐이면 보이지 않는다.
// ‹ 는 앞 묶음의 마지막 쪽(예: 7쪽 → 5쪽), › 는 다음 묶음의 첫 쪽(예: 7쪽 → 11쪽)으로 간다
export default function Pagination({
  page,
  pageCount,
  onChange,
}: {
  page: number; // 1부터
  pageCount: number;
  onChange: (page: number) => void;
}) {
  if (pageCount <= 1) return null;

  const first = Math.floor((page - 1) / GROUP) * GROUP + 1;
  const last = Math.min(first + GROUP - 1, pageCount);
  const numbers = Array.from({ length: last - first + 1 }, (_, i) => first + i);

  return (
    <nav className={styles.pagination} aria-label="쪽 이동">
      <button type="button" className={styles.button} disabled={first === 1} onClick={() => onChange(first - 1)} aria-label="이전 쪽 묶음">
        ‹
      </button>
      {numbers.map((n) => (
        <button
          key={n}
          type="button"
          className={`${styles.button} ${n === page ? styles.current : ""}`}
          aria-current={n === page ? "page" : undefined}
          onClick={() => onChange(n)}
        >
          {n}
        </button>
      ))}
      <button type="button" className={styles.button} disabled={last === pageCount} onClick={() => onChange(last + 1)} aria-label="다음 쪽 묶음">
        ›
      </button>
    </nav>
  );
}
