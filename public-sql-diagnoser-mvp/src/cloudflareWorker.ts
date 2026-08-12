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

const MAX_API_BODY_BYTES = 1024 * 1024;

const apiHandlers: Record<string, ApiHandler> = {
  "/api/ai-data-insights": handleAiDataInsightsRequest as ApiHandler,
  "/api/ai-document-draft": handleAiDocumentDraftRequest as ApiHandler,
  "/api/ai-explain": handleAiExplainRequest as ApiHandler,
  "/api/ai-multi-document-draft": handleAiMultiDocumentDraftRequest as ApiHandler,
};

const jsonResponse = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  headers: {
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
  },
  status,
});

const hasDemoAccessConfig = (env: WorkerEnv) =>
  Boolean(env.DEMO_USERNAME?.trim() && env.DEMO_PASSWORD?.trim());

const encodeBasicCredentials = (value: string) => {
  const bytes = new TextEncoder().encode(value);
  let binary = "";

  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });

  return btoa(binary);
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

const hasAuthorizedDemoAccess = (request: Request, env: WorkerEnv) => {
  if (!hasDemoAccessConfig(env)) {
    return false;
  }

  const expected = `Basic ${encodeBasicCredentials(`${env.DEMO_USERNAME}:${env.DEMO_PASSWORD}`)}`;
  const authorization = request.headers.get("Authorization") ?? "";

  return equalLengthStringsMatch(authorization, expected);
};

const unauthorizedResponse = () => new Response("Demo authentication is required.", {
  headers: {
    "Cache-Control": "no-store",
    "WWW-Authenticate": 'Basic realm="SQL Diagnoser Demo", charset="UTF-8"',
  },
  status: 401,
});

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

const handleApiRequest = async (request: Request, env: WorkerEnv, pathname: string) => {
  const handler = apiHandlers[pathname];

  if (!handler) {
    return undefined;
  }

  if (request.method !== "POST") {
    return jsonResponse({ error: "POST 요청만 지원합니다." }, 405);
  }

  if (!hasDemoAccessConfig(env)) {
    return jsonResponse({
      error: "AI 데모 접근 계정이 설정되지 않았습니다. DEMO_USERNAME과 DEMO_PASSWORD를 Worker 비밀값으로 설정하세요.",
    }, 503);
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
    const protectedDemo = hasDemoAccessConfig(env);

    if (protectedDemo && !hasAuthorizedDemoAccess(request, env)) {
      return unauthorizedResponse();
    }

    if (url.pathname === "/api/runtime-config") {
      return jsonResponse({
        aiEnabled: protectedDemo && isWorkerAiConfigured(env),
      });
    }

    const apiResponse = await handleApiRequest(request, env, url.pathname);

    if (apiResponse) {
      return apiResponse;
    }

    return env.ASSETS.fetch(request);
  },
};
