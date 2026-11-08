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
    setMe(null);
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
        {/* 내 지원 현황 화면은 아직 없어서 이동하지 않는다 */}
        {me?.role === "지원자" && <span className={styles.item}>내 지원 현황</span>}
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
