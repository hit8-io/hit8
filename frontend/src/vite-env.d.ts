/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly API_URL: string
  readonly VITE_GOOGLE_IDENTITY_PLATFORM_KEY: string
  readonly VITE_GOOGLE_IDENTITY_PLATFORM_DOMAIN: string
  readonly VITE_GCP_PROJECT: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

