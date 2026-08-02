import type { AiSqlExplanation } from "./aiExplanation.js";

export type AiExplanationState =
  | { status: "idle"; explanation?: undefined; errorMessage?: undefined }
  | { status: "loading"; explanation?: undefined; errorMessage?: undefined }
  | { status: "success"; explanation: AiSqlExplanation; errorMessage?: undefined }
  | { status: "error"; explanation?: undefined; errorMessage: string };

export const idleAiExplanationState = (): AiExplanationState => ({
  status: "idle",
});

export const loadingAiExplanationState = (): AiExplanationState => ({
  status: "loading",
});

export const successAiExplanationState = (
  explanation: AiSqlExplanation,
): AiExplanationState => ({
  explanation,
  status: "success",
});

export const errorAiExplanationState = (
  errorMessage: string,
): AiExplanationState => ({
  errorMessage,
  status: "error",
});

export const preserveAnalysisWithAiError = <TAnalysis>(
  analysis: TAnalysis,
  errorMessage: string,
) => ({
  aiState: errorAiExplanationState(errorMessage),
  analysis,
});
