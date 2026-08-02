import {
  AI_SQL_DOCUMENT_DRAFT_SCHEMA,
  buildAiSqlDocumentDraftPayload,
  normalizeAiSqlDocumentDraft,
  normalizeAiSqlDocumentType,
  type AiSqlDocumentDraftResponse,
} from "../src/aiDocumentDraft.js";
import {
  callStructuredAiProvider,
  pickAiProviderEnv,
  resolveProviderConfig,
} from "./ai-provider.js";

type AiDocumentDraftBody = {
  analysis?: unknown;
  documentType?: unknown;
  sql?: unknown;
};

type HandleAiDocumentDraftOptions = {
  env?: Record<string, string | undefined>;
  fetcher?: typeof fetch;
  maxSqlLength?: number;
};

type AiDocumentDraftResult = {
  body: AiSqlDocumentDraftResponse | { error: string };
  status: number;
};

const DEFAULT_MAX_SQL_LENGTH = 20000;

export const handleAiDocumentDraftRequest = async (
  body: AiDocumentDraftBody,
  options: HandleAiDocumentDraftOptions = {},
): Promise<AiDocumentDraftResult> => {
  const env = options.env ?? {};
  const fetcher = options.fetcher ?? fetch;
  const maxSqlLength = options.maxSqlLength ?? DEFAULT_MAX_SQL_LENGTH;
  const providerConfig = resolveProviderConfig(env);

  if ("error" in providerConfig) {
    return {
      body: { error: providerConfig.error },
      status: 500,
    };
  }

  if (typeof body.sql !== "string" || body.sql.trim().length === 0) {
    return {
      body: { error: "문서 초안을 생성할 SQL이 필요합니다." },
      status: 400,
    };
  }

  if (body.sql.length > maxSqlLength) {
    return {
      body: { error: `SQL 길이가 제한(${maxSqlLength}자)을 초과했습니다.` },
      status: 413,
    };
  }

  if (!body.analysis || typeof body.analysis !== "object") {
    return {
      body: { error: "룰 기반 분석 결과가 필요합니다." },
      status: 400,
    };
  }

  const payload = buildAiSqlDocumentDraftPayload(
    body.sql,
    body.analysis as Parameters<typeof buildAiSqlDocumentDraftPayload>[1],
    normalizeAiSqlDocumentType(body.documentType),
  );

  try {
    const draft = normalizeAiSqlDocumentDraft(
      await callStructuredAiProvider(
        providerConfig,
        {
          data: {
            analysis: payload.analysis,
            documentType: payload.documentType,
            documentTypeLabel: payload.documentTypeLabel,
            maskedSql: payload.maskedSql,
          },
          instructions: payload.instructions,
        },
        fetcher,
        {
          fallbackErrorMessage: "AI 문서 초안 생성 요청에 실패했습니다.",
          schema: AI_SQL_DOCUMENT_DRAFT_SCHEMA,
          schemaName: "ai_sql_document_draft",
        },
      ),
    );

    return {
      body: { draft },
      status: 200,
    };
  } catch (error) {
    const errorMessage = error instanceof Error
      ? error.message
      : "AI 문서 초안 생성 요청에 실패했습니다.";

    return {
      body: { error: errorMessage },
      status: 502,
    };
  }
};

const parseRequestBody = async (req: any) => {
  if (req.body && typeof req.body === "object") {
    return req.body;
  }

  if (typeof req.body === "string") {
    return JSON.parse(req.body);
  }

  const chunks: Buffer[] = [];

  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }

  const rawBody = Buffer.concat(chunks).toString("utf8");
  return rawBody ? JSON.parse(rawBody) : {};
};

export default async function handler(req: any, res: any) {
  if (req.method !== "POST") {
    res.status(405).json({ error: "POST 요청만 지원합니다." });
    return;
  }

  try {
    const body = await parseRequestBody(req);
    const result = await handleAiDocumentDraftRequest(body, {
      env: pickAiProviderEnv(process.env),
    });

    res.status(result.status).json(result.body);
  } catch {
    res.status(400).json({ error: "요청 JSON을 해석하지 못했습니다." });
  }
}
