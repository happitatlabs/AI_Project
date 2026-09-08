import type { AiSqlExplanation } from "./aiExplanation.js";

export class AiRequestCoordinator {
  private pending = new Map<string, { controller: AbortController; timer: ReturnType<typeof setTimeout> }>();

  begin(channel: string, timeoutMs = 120_000) {
    this.cancel(channel);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new DOMException("AI 응답 제한 시간을 초과했습니다. 다시 시도하세요.", "TimeoutError")), timeoutMs);
    const entry = { controller, timer };
    this.pending.set(channel, entry);
    return {
      signal: controller.signal,
      current: () => this.pending.get(channel) === entry,
      finish: () => {
        clearTimeout(timer);
        if (this.pending.get(channel) === entry) this.pending.delete(channel);
      },
    };
  }

  cancel(channel?: string) {
    for (const [key, entry] of this.pending) {
      if (channel && key !== channel) continue;
      this.pending.delete(key);
      clearTimeout(entry.timer);
      entry.controller.abort();
    }
  }
}

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
