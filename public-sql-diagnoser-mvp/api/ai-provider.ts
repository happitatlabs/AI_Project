export type AiProvider = "openai" | "ollama" | "azure_openai";

export type AiProviderConfig =
  | {
      apiKey: string;
      model: string;
      provider: "openai";
    }
  | {
      baseUrl: string;
      model: string;
      provider: "ollama";
    }
  | {
      apiKey: string;
      endpoint: string;
      model: string;
      provider: "azure_openai";
    };

export type StructuredAiPayload = {
  data: unknown;
  instructions: string;
};

type StructuredAiProviderOptions = {
  fallbackErrorMessage: string;
  schema: unknown;
  schemaName: string;
};

export const AI_PROVIDER_ENV_KEYS = [
  "AI_MODEL",
  "AI_PROVIDER",
  "AZURE_OPENAI_API_KEY",
  "AZURE_OPENAI_DEPLOYMENT",
  "AZURE_OPENAI_ENDPOINT",
  "AZURE_OPENAI_MODEL",
  "LOCAL_AI_BASE_URL",
  "LOCAL_AI_MODEL",
  "OLLAMA_BASE_URL",
  "OLLAMA_MODEL",
  "OPENAI_API_KEY",
  "OPENAI_MODEL",
] as const;

export const pickAiProviderEnv = (
  source: Record<string, string | undefined>,
) =>
  Object.fromEntries(
    AI_PROVIDER_ENV_KEYS.map((key) => [key, source[key]]),
  ) as Record<(typeof AI_PROVIDER_ENV_KEYS)[number], string | undefined>;

const jsonHeaders = {
  "Content-Type": "application/json",
};

const getEnvValue = (
  env: Record<string, string | undefined>,
  ...names: string[]
) => {
  for (const name of names) {
    const value = env[name]?.trim();

    if (value) {
      return value;
    }
  }

  return "";
};

const normalizeProviderName = (value: string): AiProvider | "" => {
  const normalized = value.trim().toLowerCase().replace(/-/g, "_");

  if (!normalized) {
    return "";
  }

  if (normalized === "local" || normalized === "ollama") {
    return "ollama";
  }

  if (normalized === "azure" || normalized === "azure_openai") {
    return "azure_openai";
  }

  if (normalized === "openai") {
    return "openai";
  }

  return "";
};

const resolveProvider = (env: Record<string, string | undefined>): AiProvider => {
  const explicitProvider = normalizeProviderName(getEnvValue(env, "AI_PROVIDER"));

  if (explicitProvider) {
    return explicitProvider;
  }

  if (getEnvValue(env, "OLLAMA_MODEL", "LOCAL_AI_MODEL", "OLLAMA_BASE_URL", "LOCAL_AI_BASE_URL")) {
    return "ollama";
  }

  if (getEnvValue(env, "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_MODEL")) {
    return "azure_openai";
  }

  return "openai";
};

const trimTrailingSlash = (value: string) => value.replace(/\/+$/, "");

export const resolveProviderConfig = (
  env: Record<string, string | undefined>,
): AiProviderConfig | { error: string } => {
  const providerName = getEnvValue(env, "AI_PROVIDER");
  const provider = resolveProvider(env);

  if (providerName && !normalizeProviderName(providerName)) {
    return {
      error: "AI_PROVIDER는 openai, ollama, azure_openai 중 하나여야 합니다.",
    };
  }

  if (provider === "ollama") {
    const model = getEnvValue(env, "OLLAMA_MODEL", "LOCAL_AI_MODEL", "AI_MODEL");

    if (!model) {
      return {
        error: "OLLAMA_MODEL 또는 AI_MODEL 환경변수가 설정되어 있지 않습니다.",
      };
    }

    return {
      baseUrl: trimTrailingSlash(
        getEnvValue(env, "OLLAMA_BASE_URL", "LOCAL_AI_BASE_URL") || "http://localhost:11434",
      ),
      model,
      provider,
    };
  }

  if (provider === "azure_openai") {
    const apiKey = getEnvValue(env, "AZURE_OPENAI_API_KEY");
    const endpoint = getEnvValue(env, "AZURE_OPENAI_ENDPOINT");
    const model = getEnvValue(env, "AZURE_OPENAI_MODEL", "AZURE_OPENAI_DEPLOYMENT", "AI_MODEL");

    if (!apiKey) {
      return {
        error: "AZURE_OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.",
      };
    }

    if (!endpoint) {
      return {
        error: "AZURE_OPENAI_ENDPOINT 환경변수가 설정되어 있지 않습니다.",
      };
    }

    if (!model) {
      return {
        error: "AZURE_OPENAI_MODEL 또는 AI_MODEL 환경변수가 설정되어 있지 않습니다.",
      };
    }

    return {
      apiKey,
      endpoint: trimTrailingSlash(endpoint),
      model,
      provider,
    };
  }

  const apiKey = getEnvValue(env, "OPENAI_API_KEY");
  const model = getEnvValue(env, "OPENAI_MODEL", "AI_MODEL");

  if (!apiKey) {
    return {
      error: "OPENAI_API_KEY 환경변수가 설정되어 있지 않습니다.",
    };
  }

  if (!model) {
    return {
      error: "OPENAI_MODEL 또는 AI_MODEL 환경변수가 설정되어 있지 않습니다.",
    };
  }

  return {
    apiKey,
    model,
    provider,
  };
};

const extractOpenAiText = (value: unknown) => {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};

  if (typeof record.output_text === "string") {
    return record.output_text;
  }

  const output = Array.isArray(record.output) ? record.output : [];

  for (const outputItem of output) {
    const outputRecord =
      outputItem && typeof outputItem === "object"
        ? outputItem as Record<string, unknown>
        : {};
    const content = Array.isArray(outputRecord.content) ? outputRecord.content : [];

    for (const contentItem of content) {
      const contentRecord =
        contentItem && typeof contentItem === "object"
          ? contentItem as Record<string, unknown>
          : {};

      if (typeof contentRecord.text === "string") {
        return contentRecord.text;
      }
    }
  }

  return "";
};

export const parseJsonFromText = (text: string) => {
  const trimmed = text.trim();

  try {
    return JSON.parse(trimmed);
  } catch {
    // Continue with defensive extraction below.
  }

  const fencedJson = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i);

  if (fencedJson?.[1]) {
    try {
      return JSON.parse(fencedJson[1].trim());
    } catch {
      // Continue with object extraction below.
    }
  }

  const firstBrace = trimmed.indexOf("{");
  const lastBrace = trimmed.lastIndexOf("}");

  if (firstBrace >= 0 && lastBrace > firstBrace) {
    return JSON.parse(trimmed.slice(firstBrace, lastBrace + 1));
  }

  throw new Error("AI 응답에서 JSON 객체를 해석하지 못했습니다.");
};

const extractErrorMessage = (
  responseBody: unknown,
  fallbackMessage: string,
) => {
  const errorRecord =
    responseBody && typeof responseBody === "object"
      ? responseBody as Record<string, unknown>
      : {};
  const nestedError =
    errorRecord.error && typeof errorRecord.error === "object"
      ? errorRecord.error as Record<string, unknown>
      : {};

  if (typeof nestedError.message === "string") {
    return nestedError.message;
  }

  if (typeof errorRecord.error === "string") {
    return errorRecord.error;
  }

  if (typeof errorRecord.message === "string") {
    return errorRecord.message;
  }

  return fallbackMessage;
};

const parseOpenAiStructuredResponse = async (
  response: Response,
  fallbackErrorMessage: string,
) => {
  const responseBody = await response.json();

  if (!response.ok) {
    throw new Error(extractErrorMessage(responseBody, fallbackErrorMessage));
  }

  const outputText = extractOpenAiText(responseBody);

  if (!outputText) {
    throw new Error("AI 응답에서 JSON 텍스트를 찾지 못했습니다.");
  }

  return parseJsonFromText(outputText);
};

const parseOllamaStructuredResponse = async (
  response: Response,
  fallbackErrorMessage: string,
) => {
  const responseBody = await response.json();

  if (!response.ok) {
    throw new Error(extractErrorMessage(responseBody, fallbackErrorMessage));
  }

  const record =
    responseBody && typeof responseBody === "object"
      ? responseBody as Record<string, unknown>
      : {};
  const message =
    record.message && typeof record.message === "object"
      ? record.message as Record<string, unknown>
      : {};
  const outputText =
    typeof message.content === "string"
      ? message.content
      : typeof record.response === "string"
        ? record.response
        : "";

  if (!outputText) {
    throw new Error("Ollama 응답에서 JSON 텍스트를 찾지 못했습니다.");
  }

  return parseJsonFromText(outputText);
};

const buildResponsesApiBody = (
  payload: StructuredAiPayload,
  model: string,
  options: StructuredAiProviderOptions,
) => ({
  input: [
    {
      content: [
        {
          text: payload.instructions,
          type: "input_text",
        },
      ],
      role: "system",
    },
    {
      content: [
        {
          text: JSON.stringify(payload.data),
          type: "input_text",
        },
      ],
      role: "user",
    },
  ],
  model,
  text: {
    format: {
      name: options.schemaName,
      schema: options.schema,
      strict: true,
      type: "json_schema",
    },
  },
});

const buildOllamaChatBody = (
  payload: StructuredAiPayload,
  model: string,
  options: StructuredAiProviderOptions,
) => ({
  format: options.schema,
  messages: [
    {
      content: `${payload.instructions}
JSON 외의 설명, 마크다운 코드블록, 접두사, 접미사는 출력하지 마라.`,
      role: "system",
    },
    {
      content: JSON.stringify(payload.data),
      role: "user",
    },
  ],
  model,
  options: {
    temperature: 0,
  },
  stream: false,
});

const buildAzureResponsesUrl = (endpoint: string) => {
  const normalizedEndpoint = trimTrailingSlash(endpoint);

  if (normalizedEndpoint.endsWith("/responses")) {
    return normalizedEndpoint;
  }

  if (normalizedEndpoint.endsWith("/openai/v1")) {
    return `${normalizedEndpoint}/responses`;
  }

  if (normalizedEndpoint.endsWith("/openai")) {
    return `${normalizedEndpoint}/v1/responses`;
  }

  return `${normalizedEndpoint}/openai/v1/responses`;
};

export const callStructuredAiProvider = async (
  config: AiProviderConfig,
  payload: StructuredAiPayload,
  fetcher: typeof fetch,
  options: StructuredAiProviderOptions,
) => {
  if (config.provider === "ollama") {
    const response = await fetcher(`${config.baseUrl}/api/chat`, {
      body: JSON.stringify(buildOllamaChatBody(payload, config.model, options)),
      headers: jsonHeaders,
      method: "POST",
    });

    return parseOllamaStructuredResponse(response, options.fallbackErrorMessage);
  }

  if (config.provider === "azure_openai") {
    const response = await fetcher(buildAzureResponsesUrl(config.endpoint), {
      body: JSON.stringify(buildResponsesApiBody(payload, config.model, options)),
      headers: {
        ...jsonHeaders,
        "api-key": config.apiKey,
      },
      method: "POST",
    });

    return parseOpenAiStructuredResponse(response, options.fallbackErrorMessage);
  }

  const response = await fetcher("https://api.openai.com/v1/responses", {
    body: JSON.stringify(buildResponsesApiBody(payload, config.model, options)),
    headers: {
      ...jsonHeaders,
      Authorization: `Bearer ${config.apiKey}`,
    },
    method: "POST",
  });

  return parseOpenAiStructuredResponse(response, options.fallbackErrorMessage);
};
