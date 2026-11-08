import styles from "./RatioBar.module.css";

type Props = {
  items: { label: string; value: number | null }[];
  // 항목 순서대로 쓰는 색 (CSS 값). 0%인 항목은 막대에서 빠지고 범례에만 남는다
  colors: string[];
  // 얇은 막대(10px). 공고 상세에서 쓴다
  thin?: boolean;
  // 항목 목록이 따로 있어 범례가 필요 없을 때
  hideLegend?: boolean;
};

// 비율 막대와 범례 (화면 09 서류·면접 평가기준)
export default function RatioBar({ items, colors, thin, hideLegend }: Props) {
  const sum = items.reduce((total, item) => total + (item.value ?? 0), 0);
  return (
    <>
      <div className={`${styles.bar} ${thin ? styles.thin : ""}`} aria-hidden="true">
        {items.map((item, i) =>
          item.value ? <span key={item.label} style={{ flexGrow: item.value, background: colors[i % colors.length] }} /> : null,
        )}
        {sum < 100 && <span style={{ flexGrow: 100 - sum }} />}
      </div>
      {!hideLegend && (
        <ul className={styles.legend}>
          {items.map((item, i) => (
            <li key={item.label} className={styles.legendItem}>
              <span className={styles.swatch} style={{ background: colors[i % colors.length] }} />
              {item.label} {item.value ?? "미입력"}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
