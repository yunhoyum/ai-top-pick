import { API_URL } from "./api";

// 면접 WebSocket 주소. 따로 정하지 않으면 main-api 주소의 http를 ws로 바꿔 쓴다
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? API_URL.replace(/^http/, "ws");

// 면접 WebSocket을 연다. 인증은 브라우저가 연결 요청에 싣는 access_token 쿠키로 한다 (코드베이스 4.5)
export function connectInterview(sessionId: number): WebSocket {
  const ws = new WebSocket(`${WS_URL}/ws/interview/${sessionId}`);
  // 질문 음성(wav)은 바이너리로 온다
  ws.binaryType = "arraybuffer";
  return ws;
}
