import { handleAiDataInsightsRequest } from "../api/ai-data-insights.js";
import { handleAiDocumentDraftRequest } from "../api/ai-document-draft.js";
import { handleAiExplainRequest } from "../api/ai-explain.js";
import { handleAiMultiDocumentDraftRequest } from "../api/ai-multi-document-draft.js";
import { pickAiProviderEnv, resolveProviderConfig } from "../api/ai-provider.js";

type WorkerAssets = {
  fetch: (request: Request) => Promise<Response>;
};

type WorkerEnv = {
  ASSETS: WorkerAssets;
  DEMO_PASSWORD?: string;
  DEMO_SESSION_SECRET?: string;
  DEMO_USERNAME?: string;
  [key: string]: WorkerAssets | string | undefined;
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
      || !equalLengthStringsMatch(parsed.username, config.username)
    ) {
      return undefined;
    }

    return {
      expiresAt: parsed.expiresAt,
      username: config.username,
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

    if (
      !equalLengthStringsMatch(username, config.username)
      || !equalLengthStringsMatch(password, config.password)
    ) {
      return jsonResponse({ error: "아이디 또는 비밀번호가 일치하지 않습니다." }, 401);
    }

    const token = await createDemoSessionToken(config);

    return jsonResponse({
      aiEnabled: isWorkerAiConfigured(env),
      authenticated: true,
      loginRequired: true,
      username: config.username,
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
  const config = getDemoAccessConfig(env);
  const session = config ? await getDemoSession(request, config) : undefined;
  const aiConfigured = isWorkerAiConfigured(env);

  return jsonResponse({
    aiConfigured,
    aiEnabled: Boolean(config && session && aiConfigured),
    authenticated: Boolean(session),
    loginRequired: Boolean(config),
    username: session?.username,
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

  const config = getDemoAccessConfig(env);

  if (!config) {
    return jsonResponse({
      error: "AI 데모 접근 계정이 설정되지 않았습니다. DEMO_USERNAME과 DEMO_PASSWORD를 Worker secret으로 설정하세요.",
    }, 503);
  }

  if (!await getDemoSession(request, config)) {
    return loginRequiredResponse();
  }

  if (!isWorkerAiConfigured(env)) {
    return jsonResponse({
      error: "AI provider 설정이 완료되지 않았습니다. Azure/OpenAI 비밀값 또는 HTTPS Ollama endpoint를 확인하세요.",
    }, 503);
  }

  try {
    const body = await parseJsonRequest(request);
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
