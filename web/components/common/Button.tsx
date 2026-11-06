import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

export default function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`${styles.button} ${className ?? ""}`} {...props} />;
}
