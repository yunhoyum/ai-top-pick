import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  // 기본은 부모 너비를 꽉 채운다. true면 글자 크기에 맞춘다
  inline?: boolean;
};

export default function Button({ variant = "primary", inline, className, ...props }: ButtonProps) {
  const classes = [styles.button, styles[variant], inline ? styles.inline : "", className ?? ""];
  return <button className={classes.join(" ")} {...props} />;
}
