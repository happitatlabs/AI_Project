# Happitat Labs Homepage

React, Vite, TypeScript, CSS Variables 기반의 Happitat Labs 홈페이지입니다.

## Local

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Cloudflare Workers Builds

- Repository: `happitatlabs/AI_Project`
- Production branch: `main`
- Root directory: `happitat-labs-homepage`
- Build command: `npm run build`
- Deploy command: `npx wrangler deploy`

정적 자산 Worker 설정은 [`wrangler.jsonc`](./wrangler.jsonc)에 있으며, Vite 빌드 결과인
`dist`를 배포하고 SPA 경로 fallback을 처리합니다.

## Links

실제 대표 노션, 이메일, GitHub 주소는 `src/content.ts`에서 교체합니다.

## Product Routes

제품 목록과 상태, 상세 경로는 `src/content.ts`의 `products` 배열에서 관리합니다.

- `/products/happy-habitat`
- `/products/sql-diagnoser`
- `/products/dot-code-editor`
