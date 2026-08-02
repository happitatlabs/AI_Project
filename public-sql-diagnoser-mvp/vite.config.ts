import { defineConfig, loadEnv, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import type { IncomingMessage, ServerResponse } from "node:http";
import { handleAiDocumentDraftRequest } from "./api/ai-document-draft";
import { handleAiExplainRequest } from "./api/ai-explain";
import { handleAiMultiDocumentDraftRequest } from "./api/ai-multi-document-draft";
import { pickAiProviderEnv } from "./api/ai-provider";

const MAX_DEV_REQUEST_BODY_LENGTH = 1024 * 1024;

const sendJson = (
  res: ServerResponse,
  status: number,
  body: unknown,
) => {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
};

const readJsonBody = async (req: IncomingMessage) => new Promise<unknown>((resolve, reject) => {
  let rawBody = "";

  req.on("data", (chunk) => {
    rawBody += Buffer.isBuffer(chunk) ? chunk.toString("utf8") : String(chunk);

    if (rawBody.length > MAX_DEV_REQUEST_BODY_LENGTH) {
      reject(new Error("request body too large"));
      req.destroy();
    }
  });

  req.on("end", () => {
    try {
      resolve(rawBody ? JSON.parse(rawBody) : {});
    } catch (error) {
      reject(error);
    }
  });
  req.on("error", reject);
});

const aiExplainLocalApiPlugin = (
  env: Record<string, string | undefined>,
): Plugin => ({
  name: "sql-explainer-local-ai-api",
  configureServer(server) {
    const mergedAiEnv = () => pickAiProviderEnv({
      ...env,
      ...process.env,
    });

    server.middlewares.use("/api/ai-explain", async (req, res) => {
      if (req.method !== "POST") {
        sendJson(res, 405, { error: "POST 요청만 지원합니다." });
        return;
      }

      try {
        const body = await readJsonBody(req);
        const result = await handleAiExplainRequest(body as Parameters<typeof handleAiExplainRequest>[0], {
          env: mergedAiEnv(),
        });

        sendJson(res, result.status, result.body);
      } catch {
        sendJson(res, 400, { error: "요청 JSON을 해석하지 못했습니다." });
      }
    });

    server.middlewares.use("/api/ai-document-draft", async (req, res) => {
      if (req.method !== "POST") {
        sendJson(res, 405, { error: "POST 요청만 지원합니다." });
        return;
      }

      try {
        const body = await readJsonBody(req);
        const result = await handleAiDocumentDraftRequest(
          body as Parameters<typeof handleAiDocumentDraftRequest>[0],
          {
            env: mergedAiEnv(),
          },
        );

        sendJson(res, result.status, result.body);
      } catch {
        sendJson(res, 400, { error: "요청 JSON을 해석하지 못했습니다." });
      }
    });

    server.middlewares.use("/api/ai-multi-document-draft", async (req, res) => {
      if (req.method !== "POST") {
        sendJson(res, 405, { error: "POST 요청만 지원합니다." });
        return;
      }

      try {
        const body = await readJsonBody(req);
        const result = await handleAiMultiDocumentDraftRequest(
          body as Parameters<typeof handleAiMultiDocumentDraftRequest>[0],
          {
            env: mergedAiEnv(),
          },
        );

        sendJson(res, result.status, result.body);
      } catch {
        sendJson(res, 400, { error: "요청 JSON을 해석하지 못했습니다." });
      }
    });
  },
});

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react(), aiExplainLocalApiPlugin(env)],
  };
});
