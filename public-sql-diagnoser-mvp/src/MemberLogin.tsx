import { useEffect, useRef, useState, type FormEvent } from "react";

export function MemberLogin({ onClose, onSignedIn, providers, registrationEnabled }: {
  onClose: () => void; onSignedIn: () => Promise<unknown>; providers: string[]; registrationEnabled: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const popup = useRef<Window | null>(null);
  const [register, setRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const receive = async (event: MessageEvent) => {
      if (event.origin !== window.location.origin || !popup.current || event.source !== popup.current || event.data?.type !== "sql-member-auth") return;
      if (!event.data.ok) { setError("소셜 로그인에 실패했습니다. 다시 시도해 주세요."); return; }
      await onSignedIn(); onClose();
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [onSignedIn, onClose]);
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const legacy = !register && (username.includes("@") || username === "test");
      const response = await fetch(register ? "/api/auth/register" : legacy ? "/api/auth/login" : "/api/auth/member-login", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "로그인하지 못했습니다.");
      setPassword(""); await onSignedIn(); onClose();
    } catch (e) { setError(e instanceof Error ? e.message : "요청을 처리하지 못했습니다."); }
    finally { setBusy(false); }
  };
  return <dialog ref={dialog} className="member-dialog" onCancel={onClose} aria-labelledby="member-title">
    <header><h2 id="member-title">{register ? "사이트 계정 가입" : "AI 이용을 위한 로그인"}</h2><button type="button" aria-label="로그인 닫기" onClick={onClose}>닫기</button></header>
    <p>일반 SQL 분석은 무료입니다. 신규 회원은 AI 이용권 1개를 받습니다.</p>
    <div className="member-socials">{[["google", "구글"], ["kakao", "카카오"], ["naver", "네이버"]].map(([id, label]) =>
      <button key={id} type="button" disabled={!providers.includes(id) || busy} onClick={() => { popup.current = window.open(`/api/auth/${id}/start`, "sql-member-login", "popup,width=500,height=700"); if (!popup.current) setError("로그인 팝업을 허용해 주세요."); }}>{label}로 계속하기{!providers.includes(id) ? " · 연결 준비 중" : ""}</button>)}</div>
    <form onSubmit={event => void submit(event)}>
      <label>아이디<input required autoComplete="username" value={username} maxLength={128} onChange={e => setUsername(e.target.value)} /></label>
      {register ? <small>영문·숫자·밑줄·마침표·하이픈 4~40자. 이메일 주소는 사용할 수 없습니다.</small> : null}
      <label>비밀번호<input required type="password" autoComplete={register ? "new-password" : "current-password"} minLength={register ? 12 : undefined} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>
      {register ? <small>비밀번호 12자 이상. 현재 비밀번호 찾기는 지원하지 않습니다.</small> : null}
      {error ? <p role="alert">{error}</p> : null}
      <button className="primary-button" disabled={busy || (register && !registrationEnabled)} type="submit">{busy ? "확인 중" : register ? "가입하기" : "로그인"}</button>
      <button type="button" disabled={busy || (!register && !registrationEnabled)} onClick={() => { setRegister(!register); setError(""); }}>{register ? "로그인으로 돌아가기" : "사이트 계정 만들기"}</button>
    </form>
  </dialog>;
}
