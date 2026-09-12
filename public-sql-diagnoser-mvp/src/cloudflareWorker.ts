import { handleAiDataInsightsRequest } from "../api/ai-data-insights.js";
import { handleAiSqlRewriteRequest } from "../api/ai-sql-rewrite.js";
import { handleAiDocumentDraftRequest } from "../api/ai-document-draft.js";
import { handleAiExplainRequest } from "../api/ai-explain.js";
import { handleAiMultiDocumentDraftRequest } from "../api/ai-multi-document-draft.js";
import { pickAiProviderEnv, resolveProviderConfig } from "../api/ai-provider.js";
import { requestQuota, type QuotaNamespace } from "./demoQuota.js";
export { DemoAiQuota } from "./demoQuota.js";
export { MemberAccount } from "./memberAccount.js";
import { memberRequest } from "./memberAccount.js";
import { clearMemberCookie, digest, localMemberLogin, memberReady, readMember, sameOrigin, type Member } from "./memberAuth.js";
import { availableProviders, handleMemberOAuth } from "./memberOAuth.js";

type WorkerAssets = {
  fetch: (request: Request) => Promise<Response>;
};

type WorkerEnv = {
  ASSETS: WorkerAssets;
  DEMO_PASSWORD?: string;
  DEMO_SESSION_SECRET?: string;
  DEMO_USERNAME?: string;
  DEMO_TEST_PASSWORD?: string;
  DEMO_AI_QUOTA?: QuotaNamespace;
  MEMBER_ACCOUNTS?: QuotaNamespace;
  [key: string]: WorkerAssets | QuotaNamespace | string | undefined;
};

type ApiRouteResult = {
  body: unknown;
  status: number;
};

type ApiHandler = (
  body: unknown,
  options: {
    env: Record<string, string | undefined>;
    fetcher: typeof fetch;
  },
) => Promise<ApiRouteResult>;

type DemoAccessConfig = {
  testPassword?: string;
  password: string;
  sessionSecret: string;
  username: string;
};

type DemoSession = {
  expiresAt: number;
  username: string;
};

const MAX_API_BODY_BYTES = 1024 * 1024;
const SESSION_COOKIE_NAME = "__Host-sql-diagnoser-demo";
const SESSION_TTL_SECONDS = 60 * 60 * 8;

const apiHandlers: Record<string, ApiHandler> = {
  "/api/ai-sql-rewrite": handleAiSqlRewriteRequest as ApiHandler,
  "/api/ai-data-insights": handleAiDataInsightsRequest as ApiHandler,
  "/api/ai-document-draft": handleAiDocumentDraftRequest as ApiHandler,
  "/api/ai-explain": handleAiExplainRequest as ApiHandler,
  "/api/ai-multi-document-draft": handleAiMultiDocumentDraftRequest as ApiHandler,
};

const jsonResponse = (
  body: unknown,
  status = 200,
  additionalHeaders: Record<string, string> = {},
) => new Response(JSON.stringify(body), {
  headers: {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
    ...additionalHeaders,
  },
  status,
});

const getDemoAccessConfig = (env: WorkerEnv): DemoAccessConfig | undefined => {
  const username = env.DEMO_USERNAME?.trim();
  const password = env.DEMO_PASSWORD;

  if (!username || !password) {
    return undefined;
  }

  return {
    testPassword: env.DEMO_TEST_PASSWORD,
    password,
    // A separate secret supports independent session invalidation. The password
    // fallback keeps existing two-variable demo deployments working safely.
    sessionSecret: env.DEMO_SESSION_SECRET?.trim() || password,
    username,
  };
};

const equalLengthStringsMatch = (left: string, right: string) => {
  if (left.length !== right.length) {
    return false;
  }

  let difference = 0;

  for (let index = 0; index < left.length; index += 1) {
    difference |= left.charCodeAt(index) ^ right.charCodeAt(index);
  }

  return difference === 0;
};

const base64UrlEncode = (value: Uint8Array) => {
  let binary = "";

  value.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });

  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
};

const base64UrlDecode = (value: string) => {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padding = "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(`${normalized}${padding}`);
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return bytes;
};

const createSessionSigningKey = (sessionSecret: string) => crypto.subtle.importKey(
  "raw",
  new TextEncoder().encode(sessionSecret),
  { hash: "SHA-256", name: "HMAC" },
  false,
  ["sign", "verify"],
);

const createDemoSessionToken = async (config: DemoAccessConfig) => {
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = base64UrlEncode(new TextEncoder().encode(JSON.stringify({
    expiresAt,
    username: config.username,
    version: 1,
  })));
  const signingKey = await createSessionSigningKey(config.sessionSecret);
  const signature = await crypto.subtle.sign(
    "HMAC",
    signingKey,
    new TextEncoder().encode(payload),
  );

  return `${payload}.${base64UrlEncode(new Uint8Array(signature))}`;
};

const parseCookieValue = (request: Request, name: string) => {
  const cookieHeader = request.headers.get("Cookie") ?? "";
  const cookie = cookieHeader
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));

  return cookie ? cookie.slice(name.length + 1) : undefined;
};

const getDemoSession = async (
  request: Request,
  config: DemoAccessConfig,
): Promise<DemoSession | undefined> => {
  const token = parseCookieValue(request, SESSION_COOKIE_NAME);

  if (!token) {
    return undefined;
  }

  const [payload, signature, ...extraSegments] = token.split(".");

  if (!payload || !signature || extraSegments.length > 0) {
    return undefined;
  }

  try {
    const signingKey = await createSessionSigningKey(config.sessionSecret);
    const valid = await crypto.subtle.verify(
      "HMAC",
      signingKey,
      base64UrlDecode(signature),
      new TextEncoder().encode(payload),
    );

    if (!valid) {
      return undefined;
    }

    const parsed = JSON.parse(new TextDecoder().decode(base64UrlDecode(payload))) as {
      expiresAt?: unknown;
      username?: unknown;
      version?: unknown;
    };

    if (
      parsed.version !== 1
      || typeof parsed.expiresAt !== "number"
      || !Number.isSafeInteger(parsed.expiresAt)
      || parsed.expiresAt <= Math.floor(Date.now() / 1000)
      || typeof parsed.username !== "string"
      || !(equalLengthStringsMatch(parsed.username, config.username) || (config.testPassword && parsed.username === "test"))
    ) {
      return undefined;
    }

    return {
      expiresAt: parsed.expiresAt,
      username: parsed.username,
    };
  } catch {
    return undefined;
  }
};

const sessionCookie = (token: string) =>
  `${SESSION_COOKIE_NAME}=${token}; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=${SESSION_TTL_SECONDS}`;

const expiredSessionCookie = () =>
  `${SESSION_COOKIE_NAME}=; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=0`;

const isUsableWorkerOllamaEndpoint = (value: string | undefined) => {
  if (!value) {
    return false;
  }

  try {
    const url = new URL(value);
    const localHosts = ["127.0.0.1", "localhost", "::1"];

    return url.protocol === "https:" && !localHosts.includes(url.hostname);
  } catch {
    return false;
  }
};

const isWorkerAiConfigured = (env: WorkerEnv) => {
  const providerEnv = pickAiProviderEnv(env as Record<string, string | undefined>);
  const providerConfig = resolveProviderConfig(providerEnv);

  if ("error" in providerConfig) {
    return false;
  }

  return providerConfig.provider !== "ollama" || isUsableWorkerOllamaEndpoint(providerConfig.baseUrl);
};

const parseJsonRequest = async (request: Request) => {
  const contentLength = Number(request.headers.get("Content-Length"));

  if (Number.isFinite(contentLength) && contentLength > MAX_API_BODY_BYTES) {
    throw new RangeError("요청 본문이 너무 큽니다.");
  }

  const rawBody = await request.text();

  if (new TextEncoder().encode(rawBody).byteLength > MAX_API_BODY_BYTES) {
    throw new RangeError("요청 본문이 너무 큽니다.");
  }

  return rawBody ? JSON.parse(rawBody) : {};
};

const loginRequiredResponse = () => jsonResponse({
  error: "AI 설명 보강은 로그인한 테스트 계정에서만 사용할 수 있습니다.",
}, 401);

const handleLoginRequest = async (request: Request, env: WorkerEnv) => {
  if (request.method !== "POST") {
    return jsonResponse({ error: "POST 요청만 지원합니다." }, 405);
  }

  const config = getDemoAccessConfig(env);

  if (!config) {
    return jsonResponse({
      error: "데모 로그인 계정이 아직 설정되지 않았습니다. DEMO_USERNAME과 DEMO_PASSWORD를 Worker secret으로 설정하세요.",
    }, 503);
  }

  try {
    const body = await parseJsonRequest(request) as { password?: unknown; username?: unknown };
    const username = typeof body.username === "string" ? body.username.trim() : "";
    const password = typeof body.password === "string" ? body.password : "";

    const primaryValid = equalLengthStringsMatch(username, config.username) && equalLengthStringsMatch(password, config.password);
    const testValid = username === "test" && Boolean(config.testPassword) && equalLengthStringsMatch(password, config.testPassword!);
    if (!primaryValid && !testValid) {
      return jsonResponse({ error: "아이디 또는 비밀번호가 일치하지 않습니다." }, 401);
    }

    const token = await createDemoSessionToken({ ...config, username });

    return jsonResponse({
      aiEnabled: isWorkerAiConfigured(env),
      authenticated: true,
      loginRequired: true,
      username,
    }, 200, {
      "Set-Cookie": sessionCookie(token),
    });
  } catch (error) {
    if (error instanceof RangeError) {
      return jsonResponse({ error: error.message }, 413);
    }

    return jsonResponse({ error: "로그인 요청 형식을 해석하지 못했습니다." }, 400);
  }
};

const handleLogoutRequest = (request: Request) => {
  if (request.method !== "POST") {
    return jsonResponse({ error: "POST 요청만 지원합니다." }, 405);
  }

  return jsonResponse({ authenticated: false }, 200, {
    "Set-Cookie": expiredSessionCookie(),
  });
};

const handleRuntimeConfigRequest = async (request: Request, env: WorkerEnv) => {
  if (env.AI_CREDITS_ENABLED === "true") {
    const member = await accessMember(request, env);
    let credits: unknown;
    let creditError = false;
    if (member) {
      try { credits = member.unlimited ? { unlimited: true, remaining: null } : await (await memberRequest(env.MEMBER_ACCOUNTS, member.id, "/balance")).json(); }
      catch { creditError = true; }
    }
    return jsonResponse({ aiConfigured: isWorkerAiConfigured(env), aiEnabled: Boolean(member && !creditError && isWorkerAiConfigured(env)), authenticated: Boolean(member),
      loginRequired: false, aiLoginRequired: true, creditsMode: true, username: member?.username, credits, creditError,
      registrationEnabled: memberReady(env), providers: availableProviders(env), paymentsEnabled: false });
  }
  const config = getDemoAccessConfig(env);
  const session = config ? await getDemoSession(request, config) : undefined;
  const aiConfigured = isWorkerAiConfigured(env);
  let quota: unknown;
  if (session?.username === "test") {
    try { quota = (await requestQuota(env.DEMO_AI_QUOTA, session.username, false)).quota; }
    catch { return jsonResponse({ error: "AI 사용량을 확인하지 못했습니다. 잠시 후 다시 시도하세요." }, 503); }
  }

  return jsonResponse({
    aiConfigured,
    aiEnabled: Boolean(config && session && aiConfigured),
    authenticated: Boolean(session),
    loginRequired: Boolean(config),
    username: session?.username,
    quota,
  });
};

const handleAuthenticationRequest = async (request: Request, env: WorkerEnv, pathname: string) => {
  if (pathname === "/api/auth/login") {
    return handleLoginRequest(request, env);
  }

  if (pathname === "/api/auth/logout") {
    return handleLogoutRequest(request);
  }

  return undefined;
};

const handleApiRequest = async (request: Request, env: WorkerEnv, pathname: string) => {
  const handler = apiHandlers[pathname];

  if (!handler) {
    return undefined;
  }

  if (request.method !== "POST") {
    return jsonResponse({ error: "POST 요청만 지원합니다." }, 405);
  }

  if (env.AI_CREDITS_ENABLED === "true") {
    if (!sameOrigin(request)) return jsonResponse({ error: "허용되지 않은 요청입니다." }, 403);
    const member = await accessMember(request, env);
    if (!member) return jsonResponse({ error: "AI 사용에는 로그인이 필요합니다.", loginRequired: true }, 401);
    if (!isWorkerAiConfigured(env)) return jsonResponse({ error: "AI 연결이 준비되지 않았습니다." }, 503);
    let reserved = false;
    const id = request.headers.get("X-Request-Id") || crypto.randomUUID();
    try {
      const body = await parseJsonRequest(request);
      if (!member.unlimited) {
        const reservation = await memberRequest(env.MEMBER_ACCOUNTS, member.id, "/reserve", { id });
        if (reservation.status === 402) return jsonResponse({ error: "AI 이용권을 모두 사용했습니다. 충전 후 다시 이용해 주세요.", quota: { remaining: 0 }, credits: { remaining: 0, unlimited: false } }, 402);
        if (!reservation.ok) return jsonResponse({ error: "요청이 중복되었거나 이용권을 확인하지 못했습니다." }, reservation.status);
        reserved = true;
      }
      const result = await handler(body, {
        env: pickAiProviderEnv(env as Record<string, string | undefined>),
        fetcher: (input, init) => fetch(input, { ...init, signal: AbortSignal.any([AbortSignal.timeout(90000), request.signal, ...(init?.signal ? [init.signal] : [])]) }),
      });
      if (reserved) {
        const settlement = await memberRequest(env.MEMBER_ACCOUNTS, member.id, result.status >= 200 && result.status < 300 && !request.signal.aborted ? "/complete" : "/release", { id });
        if (!settlement.ok) throw new Error("Credit settlement failed");
        reserved = false;
      }
      return jsonResponse(result.body, result.status);
    } catch (error) {
      return jsonResponse({ error: error instanceof RangeError ? error.message : "AI 요청을 완료하지 못했습니다. 이용권 내역을 다시 확인해 주세요." }, error instanceof RangeError ? 413 : 503);
    } finally {
      if (reserved) { try { await memberRequest(env.MEMBER_ACCOUNTS, member.id, "/release", { id }); } catch { /* Expiring reservation recovers after a storage outage. */ } }
    }
  }

  const config = getDemoAccessConfig(env);

  if (!config) {
    return jsonResponse({
      error: "AI 데모 접근 계정이 설정되지 않았습니다. DEMO_USERNAME과 DEMO_PASSWORD를 Worker secret으로 설정하세요.",
    }, 503);
  }

  const session = await getDemoSession(request, config);
  if (!session) {
    return loginRequiredResponse();
  }

  if (!isWorkerAiConfigured(env)) {
    return jsonResponse({
      error: "AI provider 설정이 완료되지 않았습니다. Azure/OpenAI 비밀값 또는 HTTPS Ollama endpoint를 확인하세요.",
    }, 503);
  }

  try {
    const body = await parseJsonRequest(request);
    if (session.username === "test") {
      try {
        const usage = await requestQuota(env.DEMO_AI_QUOTA, session.username, true);
        if (usage.status === 429) return jsonResponse({ error: "오늘 AI 사용 한도 10회를 모두 사용했습니다. 한국시간 자정 이후 다시 사용할 수 있습니다.", quota: usage.quota }, 429);
      } catch {
        return jsonResponse({ error: "AI 사용량을 확인하지 못했습니다. 잠시 후 다시 시도하세요." }, 503);
      }
    }
    const result = await handler(body, {
      env: pickAiProviderEnv(env as Record<string, string | undefined>),
      fetcher: fetch,
    });

    return jsonResponse(result.body, result.status);
  } catch (error) {
    if (error instanceof RangeError) {
      return jsonResponse({ error: error.message }, 413);
    }

    return jsonResponse({ error: "요청 JSON을 해석하지 못했습니다." }, 400);
  }
};

export default {
  async fetch(request: Request, env: WorkerEnv): Promise<Response> {
    const url = new URL(request.url);

    if (env.AI_CREDITS_ENABLED === "true") {
      const social = await handleMemberOAuth(request, env);
      if (social) return social;
      if (url.pathname === "/api/auth/register" || url.pathname === "/api/auth/member-login") return localMemberLogin(request, env, url.pathname.endsWith("register"));
      if (request.method === "POST" && url.pathname.startsWith("/api/auth/") && !sameOrigin(request)) return jsonResponse({ error: "허용되지 않은 요청입니다." }, 403);
      if (url.pathname === "/api/auth/login" && request.method === "POST") {
        try {
          const limit = await memberRequest(env.MEMBER_ACCOUNTS, `auth-ip:${await digest(request.headers.get("CF-Connecting-IP") || "unknown")}`, "/throttle", {});
          if (!limit.ok) return limit;
        } catch { return jsonResponse({ error: "로그인 서비스를 확인하지 못했습니다." }, 503); }
      }
      if (url.pathname === "/api/auth/logout") {
        if (request.method !== "POST") return new Response(null, { status: 405 });
        const headers = new Headers({ "Cache-Control": "no-store" });
        headers.append("Set-Cookie", expiredSessionCookie()); headers.append("Set-Cookie", clearMemberCookie());
        return new Response(JSON.stringify({ authenticated: false }), { headers });
      }
      if (url.pathname === "/api/credits/cancel") {
        if (request.method !== "POST" || !sameOrigin(request)) return new Response(null, { status: 403 });
        const member = await accessMember(request, env);
        if (!member) return jsonResponse({ error: "로그인이 필요합니다." }, 401);
        if (member.unlimited) return jsonResponse({ ok: true });
        try {
          const body = await parseJsonRequest(request) as { id?: unknown };
          return await memberRequest(env.MEMBER_ACCOUNTS, member.id, "/release", { id: body.id });
        } catch { return jsonResponse({ error: "취소 상태를 확인하지 못했습니다." }, 503); }
      }
      if (url.pathname.startsWith("/api/credits/") || url.pathname.startsWith("/api/payments/")) return jsonResponse({ error: "결제 서비스 연결 전입니다. 현재 결제나 충전은 지원하지 않습니다." }, 503);
    }

    if (url.pathname === "/api/runtime-config") {
      return handleRuntimeConfigRequest(request, env);
    }

    const authenticationResponse = await handleAuthenticationRequest(request, env, url.pathname);

    if (authenticationResponse) {
      return authenticationResponse;
    }

    const apiResponse = await handleApiRequest(request, env, url.pathname);

    if (apiResponse) {
      return apiResponse;
    }

    return env.ASSETS.fetch(request);
  },
};

async function accessMember(request: Request, env: WorkerEnv): Promise<Member | undefined> {
  const member = await readMember(request, env);
  if (member) return member;
  const config = getDemoAccessConfig(env);
  const legacy = config ? await getDemoSession(request, config) : undefined;
  if (!legacy) return;
  return { id: `legacy:${legacy.username}`, username: legacy.username,
    unlimited: legacy.username.toLowerCase() === "plushome58@naver.com" && legacy.username === config!.username };
}
