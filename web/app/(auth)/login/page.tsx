import { Suspense } from "react";
import LoginForm from "./LoginForm";

export default function LoginPage() {
  // LoginForm이 주소의 next 값을 읽는다
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
