// File Path: frontend/src/env.d.ts
// Timestamp: 2026-05-25T12:00:00+08:00
// Version: v0.1

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>;
  export default component;
}

interface ImportMeta {
  readonly env: Record<string, string | boolean | undefined>;
}

interface ImportMetaEnv {
  readonly [key: string]: string | boolean | undefined;
}
