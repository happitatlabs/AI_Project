import type { AiDataInsightsResult } from "./aiDataInsights.js";

export type AiDataInsightsState =
  | { status: "idle"; insights?: undefined; errorMessage?: undefined }
  | { status: "loading"; insights?: undefined; errorMessage?: undefined }
  | { status: "success"; insights: AiDataInsightsResult; errorMessage?: undefined }
  | { status: "error"; insights?: undefined; errorMessage: string };

export const idleAiDataInsightsState = (): AiDataInsightsState => ({ status: "idle" });

export const loadingAiDataInsightsState = (): AiDataInsightsState => ({ status: "loading" });

export const successAiDataInsightsState = (
  insights: AiDataInsightsResult,
): AiDataInsightsState => ({ insights, status: "success" });

export const errorAiDataInsightsState = (
  errorMessage: string,
): AiDataInsightsState => ({ errorMessage, status: "error" });
