import BrandLogo from "./BrandLogo";
import styles from "./AuthBrandPanel.module.css";

const FEATURES = ["평가 기준 기반 서류 분석", "지원자 맞춤 질문과 꼬리 질문", "전형별 결과 보고서와 순위"];

// 로그인(01)·회원가입(02) 화면 왼쪽 브랜드 패널
export default function AuthBrandPanel() {
  return (
    <aside className={styles.panel}>
      <BrandLogo />
      <div className={styles.spacer} />
      <div className={styles.message}>
        <h2 className={styles.title}>
          서류부터 면접까지,
          <br />
          AI가 평가 근거를 정리합니다
        </h2>
        <p className={styles.desc}>
          회사가 정한 평가 기준으로 지원자의 서류와 면접을 분석하고,
          <br />
          전형별 결과 보고서로 제공합니다.
        </p>
        <ul className={styles.features}>
          {FEATURES.map((text) => (
            <li key={text} className={styles.feature}>
              <span className={styles.check}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/brand/check.svg" alt="" width={12} height={12} />
              </span>
              {text}
            </li>
          ))}
        </ul>
      </div>
      <div className={styles.spacer} />
    </aside>
  );
}
