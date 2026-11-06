import styles from "./BrandLogo.module.css";

// Figma Brand/Logo (150 x 35.8)
export default function BrandLogo() {
  return (
    <div className={styles.logo} role="img" aria-label="AI top-pick">
      <div className={styles.mark}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/logo-mark.svg" alt="" />
      </div>
      <div className={styles.text}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/brand/logo-text.svg" alt="" />
      </div>
    </div>
  );
}
