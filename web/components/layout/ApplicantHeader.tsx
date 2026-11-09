"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchMeIfLoggedIn, logout, type Me } from "@/lib/auth";
import BrandLogo from "./BrandLogo";
import styles from "./ApplicantHeader.module.css";

// 지원자 화면 위쪽 (Figma Applicant/Header). 비로그인도 쓰는 화면이라 로그인 여부에 따라 오른쪽이 달라진다
export default function ApplicantHeader() {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    fetchMeIfLoggedIn().then((m) => {
      setMe(m);
      setChecked(true);
    });
  }, []);

  async function onLogout() {
    await logout();
    // 지원서 작성 같은 로그인 전용 화면에 남지 않게 채용공고 목록으로 보낸다.
    // 화면을 새로 불러와서 이전 로그인 상태로 남아 있던 값(관리자 안내 문구, 작성 중이던 지원서)도 함께 지운다
    window.location.assign("/postings");
  }

  return (
    <header className={styles.header}>
      <Link href="/postings" aria-label="AI top-pick">
        <BrandLogo />
      </Link>
      <nav className={styles.menu}>
        <Link href="/postings" className={styles.item}>
          채용공고
        </Link>
        {me?.role === "지원자" && (
          <Link href="/applications" className={styles.item}>
            내 지원 현황
          </Link>
        )}
        {checked && <div className={styles.divider} />}
        {checked && me && (
          <>
            <span className={styles.user}>{me.name} 님</span>
            <button type="button" className={styles.action} onClick={onLogout}>
              로그아웃
            </button>
          </>
        )}
        {checked && !me && (
          <Link href="/login" className={styles.login}>
            로그인
          </Link>
        )}
      </nav>
    </header>
  );
}
