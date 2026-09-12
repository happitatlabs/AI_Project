import { memberRequest } from "./memberAccount.js";
import type { QuotaNamespace } from "./demoQuota.js";

export type Member = { id: string; username: string; unlimited: boolean };
export type MemberEnv = { MEMBER_ACCOUNTS?: QuotaNamespace; DEMO_SESSION_SECRET?: string; DEMO_USERNAME?: string };
const COOKIE = "__Host-sql-member";
const encoder = new TextEncoder();
export const encode = (bytes: Uint8Array) => btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const decode = (text: string) => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
export const digest = async (text: string) => encode(new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(text))));
export const cookieValue = (request: Request, name: string) => request.headers.get("Cookie")?.split(";").map(s => s.trim()).find(s => s.startsWith(`${name}=`))?.slice(name.length + 1);
const key = (secret: string) => crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
export async function sign(value: unknown, secret: string) {
  const payload = encode(encoder.encode(JSON.stringify(value)));
  return `${payload}.${encode(new Uint8Array(await crypto.subtle.sign("HMAC", await key(secret), encoder.encode(payload))))}`;
}
export async function verify(token: string | undefined, secret: string): Promise<Record<string, unknown> | undefined> {
  if (!token || token.length > 4096) return;
  try {
    const [payload, signature, extra] = token.split(".");
    if (!payload || !signature || extra || !await crypto.subtle.verify("HMAC", await key(secret), decode(signature), encoder.encode(payload))) return;
    const value = JSON.parse(new TextDecoder().decode(decode(payload)));
    if (typeof value.expires !== "number" || value.expires < Date.now()) return;
    return value;
  } catch { return; }
}
export const memberCookie = async (member: Member, secret: string) => `${COOKIE}=${await sign({ ...member, expires: Date.now() + 28800000 }, secret)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=28800`;
export const clearMemberCookie = () => `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
export async function readMember(request: Request, env: MemberEnv): Promise<Member | undefined> {
  if (!env.DEMO_SESSION_SECRET) return;
  const data = await verify(cookieValue(request, COOKIE), env.DEMO_SESSION_SECRET);
  if (!data || typeof data.id !== "string" || typeof data.username !== "string" || typeof data.unlimited !== "boolean") return;
  return { id: data.id, username: data.username, unlimited: data.unlimited };
}
export const sameOrigin = (request: Request) => request.headers.get("Origin") === new URL(request.url).origin;
export const memberReady = (env: MemberEnv) => Boolean(env.MEMBER_ACCOUNTS && env.DEMO_SESSION_SECRET && env.DEMO_SESSION_SECRET.length >= 32);
async function passwordHash(password: string, salt: string) {
  const material = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveBits"]);
  return encode(new Uint8Array(await crypto.subtle.deriveBits({ name: "PBKDF2", salt: decode(salt), iterations: 100000, hash: "SHA-256" }, material, 256)));
}
export async function localMemberLogin(request: Request, env: MemberEnv, register: boolean): Promise<Response> {
  if (!memberReady(env)) return Response.json({ error: "회원 서비스 설정이 필요합니다." }, { status: 503 });
  if (request.method !== "POST" || !sameOrigin(request)) return new Response(null, { status: 403 });
  const limited = await memberRequest(env.MEMBER_ACCOUNTS, `auth-ip:${await digest(request.headers.get("CF-Connecting-IP") || "unknown")}`, "/throttle", {});
  if (!limited.ok) return limited;
  try {
    const raw = await request.text();
    if (raw.length > 2048) return new Response(null, { status: 413 });
    const body = JSON.parse(raw);
    const username = typeof body.username === "string" ? body.username.trim().toLowerCase() : "";
    const password = typeof body.password === "string" ? body.password : "";
    // Site IDs are not verified email identities. Reserve all legacy/test administrator names.
    if (!/^[a-z0-9][a-z0-9_.-]{3,39}$/.test(username) || username === "test" || username === env.DEMO_USERNAME?.toLowerCase() || password.length < 12 || password.length > 128) {
      return Response.json({ error: "아이디는 영문·숫자 등 4~40자, 비밀번호는 12~128자로 입력하세요. 이메일 주소는 사이트 아이디로 사용할 수 없습니다." }, { status: 400 });
    }
    const id = `local:${await digest(username)}`;
    const accountLimit = await memberRequest(env.MEMBER_ACCOUNTS, `auth-account:${id}`, "/throttle", {});
    if (!accountLimit.ok) return accountLimit;
    if (register) {
      const salt = encode(crypto.getRandomValues(new Uint8Array(16)));
      const response = await memberRequest(env.MEMBER_ACCOUNTS, id, "/register", { salt, hash: await passwordHash(password, salt) });
      if (!response.ok) return response;
    } else {
      const stored = await (await memberRequest(env.MEMBER_ACCOUNTS, id, "/credential")).json() as { salt: string; hash: string } | null;
      const actual = await passwordHash(password, stored?.salt ?? encode(new Uint8Array(16)));
      let difference = actual.length ^ (stored?.hash.length ?? 0);
      for (let i = 0; i < actual.length; i++) difference |= actual.charCodeAt(i) ^ (stored?.hash.charCodeAt(i) ?? 0);
      if (!stored || difference) return Response.json({ error: "아이디 또는 비밀번호가 일치하지 않습니다." }, { status: 401 });
    }
    return Response.json({ authenticated: true }, { headers: { "Set-Cookie": await memberCookie({ id, username, unlimited: false }, env.DEMO_SESSION_SECRET!), "Cache-Control": "no-store" } });
  } catch { return Response.json({ error: "회원 요청을 처리하지 못했습니다." }, { status: 400 }); }
}
