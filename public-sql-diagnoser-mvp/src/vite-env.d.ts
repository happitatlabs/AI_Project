/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEMO_MODE?: string;
  readonly VITE_ENABLE_AI_FEATURES?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
