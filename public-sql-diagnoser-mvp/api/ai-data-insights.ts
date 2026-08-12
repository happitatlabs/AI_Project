import {
  AI_DATA_INSIGHTS_SCHEMA,
  buildAiDataInsightsPayload,
  isComputedAnalysisResult,
  normalizeAiDataInsights,
  type AiDataInsightsResponse,
} from "../src/aiDataInsights.js";
import type { SqlAnalysisResult } from "../src/sqlExplainer.js";
import {
  callStructuredAiProvider,
  pickAiProviderEnv,
  resolveProviderConfig,
} from "./ai-provider.js";

type AiDataInsightsBody = {
  computedAnalysis?: unknown;
  sqlAnalysis?: unknown;
};

type HandleAiDataInsightsOptions = {
  env?: Record<string, string | undefined>;
  fetcher?: typeof fetch;
};

type AiDataInsightsRouteResult = {
  body: AiDataInsightsResponse | { error: string };
  status: number;
};

export const handleAiDataInsightsRequest = async (
  body: AiDataInsightsBody,
  options: HandleAiDataInsightsOptions = {},
): Promise<AiDataInsightsRouteResult> => {
  const env = options.env ?? {};
  const fetcher = options.fetcher ?? fetch;

  if (!isComputedAnalysisResult(body.computedAnalysis)) {
    return {
      body: { error: "기계식 계산 결과 계약이 유효하지 않습니다. 최신 계산을 다시 실행하세요. 원본 행 데이터는 AI 요청에 사용할 수 없습니다." },
      status: 400,
    };
  }

  if (
    body.computedAnalysis &&
    typeof body.computedAnalysis === "object" &&
    "rows" in body.computedAnalysis
  ) {
    return {
      body: { error: "원본 행 데이터는 AI 요청에 포함할 수 없습니다. 기계식 계산 결과만 전송하세요." },
      status: 400,
    };
  }

  const computedAnalysis = body.computedAnalysis;

  if (computedAnalysis.insightCandidates.length === 0) {
    return {
      body: { error: "AI 해석할 인사이트 후보가 없습니다. 계산 결과와 주의 사항을 먼저 확인하세요." },
      status: 400,
    };
  }

  const providerConfig = resolveProviderConfig(env);

  if ("error" in providerConfig) {
    return {
      body: { error: providerConfig.error },
      status: 500,
    };
  }

  const payload = buildAiDataInsightsPayload(
    computedAnalysis,
    body.sqlAnalysis as SqlAnalysisResult | undefined,
  );

  try {
    const insights = normalizeAiDataInsights(
      await callStructuredAiProvider(
        providerConfig,
        {
          data: {
            computedAnalysis: payload.computedAnalysis,
            sqlContext: payload.sqlContext,
          },
          instructions: payload.instructions,
        },
        fetcher,
        {
          fallbackErrorMessage: "AI 데이터 인사이트 요청에 실패했습니다.",
          schema: AI_DATA_INSIGHTS_SCHEMA,
          schemaName: "ai_data_insights",
        },
      ),
      computedAnalysis,
    );

    return {
      body: { insights },
      status: 200,
    };
  } catch (error) {
    return {
      body: {
        error: error instanceof Error ? error.message : "AI 데이터 인사이트 요청에 실패했습니다.",
      },
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
    const result = await handleAiDataInsightsRequest(body, {
      env: pickAiProviderEnv(process.env),
    });

    res.status(result.status).json(result.body);
  } catch {
    res.status(400).json({ error: "요청 JSON을 해석하지 못했습니다." });
  }
}
