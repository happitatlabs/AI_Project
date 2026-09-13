# Membership and AI credits

## Implemented locally

- Initial page, SQL diagnosis, change comparison and rule-based reports do not require login.
- AI actions open a login dialog without discarding the input.
- Site username/password registration and login. Passwords use salted PBKDF2-SHA256, 100,000 iterations; plaintext passwords are not stored.
- Social authorization-code flows for Google, Kakao and Naver. Buttons remain disabled until provider credentials and origin are configured.
- Each new immutable member ID receives 10 initial Credits, once per account.
- Costs are defined in `src/creditPolicy.ts`: single SQL AI explanation/documentation 1, multi SQL AI explanation/documentation 2, data insights and SQL recommendations 3.
- The server derives cost from the route and SQL. A submitted cost or unlimited flag cannot override it. Multi explanation mode costs 2 even with one statement. Multi-statement SQL on the single route costs 2; quoted semicolons and comments do not create extra statements.
- The browser refreshes balance before sending an AI request; the server atomically checks the required cost again. A balance of 1 cannot start a 3-Credit request.
- A per-member SQLite Durable Object transaction reserves credits. Success commits; handler errors release. Duplicate request IDs cannot invoke the provider twice.
- Cancellation attempts to release an in-progress reservation. A completed request is not refunded by a later cancellation. Undelivered/abandoned reservations recover after ten minutes; provider calls have a 90-second upper bound.
- All five AI routes share the wallet, including SQL recommendations and data insights.
- A sticky balance bar remains visible during scrolling. AI action buttons show their Credit cost. Usage history is private to the current member and paginated in groups of 50.
- History records timestamp, operation, used Credits, balance change and remaining Credits. Reservation deducts the balance, completion confirms usage with zero additional balance change, and failure/cancellation returns the exact reserved amount. Unlimited requests are recorded with zero charge.
- Existing v1 wallets are upgraded transactionally without refilling the balance. Their history starts with the known opening balance; prior event timestamps/balances are not reconstructed. In-flight v1 requests still refund exactly 1 Credit.
- Credit shortage does not block rule-based SQL work. No purchase endpoint accepts user-supplied quantities or payment-success claims.

## Unlimited test account

The existing primary `DEMO_USERNAME=plushome58@naver.com` account is unlimited only after the existing password/session authentication succeeds. Do not change or publish its password.
Site signup rejects email-address IDs and reserves the legacy/test IDs. Display names never grant privileges.
For Google/Kakao, only a server-fetched, explicitly verified email matching this address grants the same test privilege. Naver currently uses the stable provider ID without treating its email text as verified; it does not automatically inherit unlimited access. The existing primary password login remains the supported path for this test account.

## Deployment prerequisites

- Keep current AI provider and legacy login secrets unchanged.
- `DEMO_SESSION_SECRET`: independently set random secret, at least 32 characters. Required for member registration and social authentication.
- `MEMBER_ACCOUNTS`: new SQLite Durable Object binding and `member-credits-v1` migration in wrangler.jsonc. Do not remove the existing quota migration/class; old data is not reused as a wallet.
- `AI_CREDITS_ENABLED=true`: selects the new server policy. Existing daily-quota tests remain for legacy mode but that policy is not selected by the new configuration.
- `PUBLIC_ORIGIN`: exact deployed HTTPS origin. OAuth callbacks reject other origins.
- Existing `test` credentials can still sign in when configured, but receive a one-time wallet rather than ten requests daily.

For each provider, register these server secrets (never VITE variables or repository files):

| Provider | Client credentials | Redirect URI |
| --- | --- | --- |
| Google | OAUTH_GOOGLE_CLIENT_ID, OAUTH_GOOGLE_CLIENT_SECRET | https://sql-diagnoser-demo.pletta900114.workers.dev/api/auth/google/callback |
| Kakao | OAUTH_KAKAO_CLIENT_ID (REST API key), OAUTH_KAKAO_CLIENT_SECRET | https://sql-diagnoser-demo.pletta900114.workers.dev/api/auth/kakao/callback |
| Naver | OAUTH_NAVER_CLIENT_ID, OAUTH_NAVER_CLIENT_SECRET | https://sql-diagnoser-demo.pletta900114.workers.dev/api/auth/naver/callback |

Register service domains, consent screens and production permissions with each provider. Google requests openid/email; Kakao/Naver can sign in by stable subject without requiring an email. OAuth uses a signed, expiring HttpOnly state cookie; Google additionally uses PKCE. Access tokens remain server-side and are not persisted. Successful callbacks notify only the original same-origin login window; they do not send credentials to the parent page.

## Payments: not enabled

Credit pack catalog: 30 / 100 / 300 Credits, prices not yet specified. `GET /api/credits/packs` provides the public catalog; purchase buttons remain disabled. Actual checkout, payment confirmation, purchased-credit issuance, refunds and payment history are NOT implemented. The public payments/grant routes fail closed and the UI explicitly says charging is pending.
Before implementation, choose a PG, merchant account, credit package price/currency and refund policy. Credit issuance must follow a server-verified payment amount/order and a unique payment ledger entry, not a browser success redirect. Do not enable a mock payment in production.

## Remaining launch work

- Real provider consent/login verification with configured developer apps. Current automated tests mock provider responses; they are not production OAuth verification.
- Password recovery, account deletion and explicit account linking are not implemented. Do not market this as a complete commercial membership system yet.
- Provider identities and site IDs are separate accounts; no email-based auto-linking. Multiple accounts can receive separate trials. IP/account throttling (20 auth attempts/hour) is an initial safeguard, not strong person-level anti-abuse. Consider verified signup/CAPTCHA before open promotion.
- Credits are internal AI usage units, not model input/output tokens. There is no subscription or recurring billing.
- SQL is not stored in the member/wallet ledger. It stores credential hashes, balance, opaque request IDs, operation codes and credit events.
- A cancelled client connection may race with completed provider work; completed requests stay charged. Explicit cancellation and timeout recovery cover pending reservations, not a general payment refund policy.

## Verification

`npm test` includes legacy regressions, change comparison and `tests/member-credits.test.mjs`.
The suite uses Node's SQLite engine and checks 10-Credit signup, operation pricing, positive-but-insufficient balances, concurrent reservations, idempotency, variable-cost refunds, expiry, history isolation/pagination, v1 migration, unlimited authorization, disabled packs/payments and OAuth state.
`npm run build` checks types and assets. `npx wrangler deploy --dry-run` checks the Worker bundle and bindings without deployment.
Local Wrangler UI verified (2026-09-13): guest SQL access, registration with 10 Credits, persistent balance, usage history, sticky balance bar, insufficient-credit preflight without an AI call, and disabled pack purchase at 1360/390/320px. Browser balance shortage and AI availability were simulated; registration, wallet and history used the local Worker and its SQLite storage. No actual paid transaction or external AI charge was made. Windows local persistence uses a short temporary path to avoid long-path storage errors.

Official integration references:
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.kakao.com/docs/ko/kakaologin/rest-api
- https://developers.naver.com/docs/login/api/api.md
- https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/
