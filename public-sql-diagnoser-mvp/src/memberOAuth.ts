import { cookieValue, digest, encode, memberCookie, memberReady, sign, verify, type MemberEnv } from "./memberAuth.js";

type Env = MemberEnv & { [key: string]: unknown };
const providers = {
  google: { authorize: "https://accounts.google.com/o/oauth2/v2/auth", token: "https://oauth2.googleapis.com/token", profile: "https://openidconnect.googleapis.com/v1/userinfo", scope: "openid email" },
  kakao: { authorize: "https://kauth.kakao.com/oauth/authorize", token: "https://kauth.kakao.com/oauth/token", profile: "https://kapi.kakao.com/v2/user/me", scope: "" },
  naver: { authorize: "https://nid.naver.com/oauth2.0/authorize", token: "https://nid.naver.com/oauth2.0/token", profile: "https://openapi.naver.com/v1/nid/me", scope: "" },
};
export type SocialProvider = keyof typeof providers;
export const availableProviders = (env: Env) => Object.keys(providers).filter(p => memberReady(env) && env.PUBLIC_ORIGIN && env[`OAUTH_${p.toUpperCase()}_CLIENT_ID`] && env[`OAUTH_${p.toUpperCase()}_CLIENT_SECRET`]);
const stateCookie = (value: string, age: number) => `__Host-sql-oauth=${value}; Secure; HttpOnly; SameSite=Lax; Path=/; Max-Age=${age}`;
const finishLogin = (headers: Headers, origin: string, ok: boolean) => {
  const nonce = encode(crypto.getRandomValues(new Uint8Array(16)));
  headers.set("Content-Type", "text/html; charset=utf-8");
  headers.set("Content-Security-Policy", `default-src 'none'; script-src 'nonce-${nonce}'; base-uri 'none'; frame-ancestors 'none'`);
  return new Response(`<!doctype html><html lang="ko"><meta charset="utf-8"><title>SQL Diagnoser 로그인</title><p>${ok ? "로그인되었습니다. 원래 창으로 돌아가세요." : "로그인하지 못했습니다. 원래 창에서 다시 시도하세요."}</p><script nonce="${nonce}">if(window.opener){window.opener.postMessage({type:'sql-member-auth',ok:${ok}},${JSON.stringify(origin)});window.close();}else{location.replace('/');}</script></html>`, { headers });
};

export async function handleMemberOAuth(request: Request, env: Env): Promise<Response | undefined> {
  const url = new URL(request.url);
  const match = /^\/api\/auth\/(google|kakao|naver)\/(start|callback)$/.exec(url.pathname);
  if (!match) return;
  const provider = match[1] as SocialProvider;
  if (request.method !== "GET") return new Response(null, { status: 405 });
  if (!availableProviders(env).includes(provider) || url.origin !== env.PUBLIC_ORIGIN) return Response.json({ error: "아직 연결되지 않은 로그인 서비스입니다." }, { status: 503 });
  const config = providers[provider];
  const id = String(env[`OAUTH_${provider.toUpperCase()}_CLIENT_ID`]);
  const secret = String(env[`OAUTH_${provider.toUpperCase()}_CLIENT_SECRET`]);
  const callback = `${url.origin}/api/auth/${provider}/callback`;
  if (match[2] === "start") {
    const state = encode(crypto.getRandomValues(new Uint8Array(32)));
    const verifier = encode(crypto.getRandomValues(new Uint8Array(32)));
    const cookie = await sign({ state, verifier, provider, expires: Date.now() + 600000 }, env.DEMO_SESSION_SECRET!);
    const target = new URL(config.authorize);
    target.search = new URLSearchParams({ client_id: id, redirect_uri: callback, response_type: "code", state, ...(config.scope ? { scope: config.scope } : {}) }).toString();
    if (provider === "google") { target.searchParams.set("code_challenge", await digest(verifier)); target.searchParams.set("code_challenge_method", "S256"); }
    return new Response(null, { status: 302, headers: { Location: target.href, "Set-Cookie": stateCookie(cookie, 600), "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
  }
  const headers = new Headers({ "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" });
  headers.append("Set-Cookie", stateCookie("", 0));
  try {
    const data = await verify(cookieValue(request, "__Host-sql-oauth"), env.DEMO_SESSION_SECRET!);
    if (!data || data.provider !== provider || typeof data.state !== "string" || data.state !== url.searchParams.get("state") || !url.searchParams.get("code") || url.searchParams.has("error")) throw new Error("Invalid callback");
    const response = await fetch(config.token, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, signal: AbortSignal.timeout(15000), body: new URLSearchParams({
      grant_type: "authorization_code", client_id: id, client_secret: secret, code: url.searchParams.get("code")!, redirect_uri: callback, state: data.state,
      ...(provider === "google" ? { code_verifier: String(data.verifier) } : {}),
    }) });
    const token = await response.json() as { access_token?: string };
    if (!response.ok || !token.access_token) throw new Error("Token exchange failed");
    const userResponse = await fetch(config.profile, { headers: { Authorization: `Bearer ${token.access_token}` }, signal: AbortSignal.timeout(15000) });
    const user = await userResponse.json() as Record<string, any>;
    if (!userResponse.ok) throw new Error("Profile failed");
    const subject = provider === "google" ? user.sub : provider === "naver" ? user.response?.id : user.id;
    if ((typeof subject !== "string" && typeof subject !== "number") || !String(subject)) throw new Error("Missing subject");
    // Email text is not an identity key. Never auto-link different providers by email.
    const verifiedEmail = provider === "google" && user.email_verified === true ? user.email
      : provider === "kakao" && user.kakao_account?.is_email_verified === true && user.kakao_account?.is_email_valid === true ? user.kakao_account.email : undefined;
    const memberId = `${provider}:${await digest(String(subject))}`;
    const unlimited = typeof verifiedEmail === "string" && verifiedEmail.toLowerCase() === "plushome58@naver.com";
    headers.append("Set-Cookie", await memberCookie({ id: memberId, username: typeof verifiedEmail === "string" ? verifiedEmail : `${provider} 회원`, unlimited }, env.DEMO_SESSION_SECRET!));
    return finishLogin(headers, url.origin, true);
  } catch {
    return finishLogin(headers, url.origin, false);
  }
}
