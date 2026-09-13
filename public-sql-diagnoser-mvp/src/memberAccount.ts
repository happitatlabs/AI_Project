import type { QuotaNamespace } from "./demoQuota.js";
import { CREDIT_OPERATIONS, SIGNUP_CREDITS, type CreditOperation } from "./creditPolicy.js";

export type CreditEvent = {
  seq: number; at: number; kind: string; operation: string; used: number; delta: number; remaining: number;
};
type Reservation = { id: string; status: string; charged: number; operation: string; unlimited: number };

type Storage = {
  sql: { exec<T>(query: string, ...params: (string | number)[]): { toArray(): T[] } };
  transactionSync<T>(callback: () => T): T;
};

// One object per immutable member ID. The trial and ledger survive sessions and deploys.
export class MemberAccount {
  constructor(private ctx: { storage: Storage }) {
    const sql = ctx.storage.sql;
    sql.exec("CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY, balance INTEGER NOT NULL CHECK(balance >= 0))");
    sql.exec("CREATE TABLE IF NOT EXISTS ledger (id TEXT PRIMARY KEY, status TEXT NOT NULL, expires INTEGER NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS credential (id INTEGER PRIMARY KEY, salt TEXT NOT NULL, hash TEXT NOT NULL)");
    sql.exec("CREATE TABLE IF NOT EXISTS throttle (id INTEGER PRIMARY KEY, window INTEGER NOT NULL, used INTEGER NOT NULL)");
    ctx.storage.transactionSync(() => {
      const columns = new Set(sql.exec<{ name: string }>("PRAGMA table_info(ledger)").toArray().map(column => column.name));
      if (!columns.has("charged")) sql.exec("ALTER TABLE ledger ADD COLUMN charged INTEGER NOT NULL DEFAULT 1");
      if (!columns.has("operation")) sql.exec("ALTER TABLE ledger ADD COLUMN operation TEXT NOT NULL DEFAULT 'legacy'");
      if (!columns.has("unlimited")) sql.exec("ALTER TABLE ledger ADD COLUMN unlimited INTEGER NOT NULL DEFAULT 0");
      sql.exec("CREATE TABLE IF NOT EXISTS credit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL, kind TEXT NOT NULL, operation TEXT NOT NULL, used INTEGER NOT NULL, delta INTEGER NOT NULL, remaining INTEGER NOT NULL)");
      const wallet = sql.exec<{ balance: number }>("SELECT balance FROM wallet WHERE id=1").toArray()[0];
      if (wallet && !sql.exec("SELECT seq FROM credit_events LIMIT 1").toArray().length) {
        // Old wallets have no historical balance snapshots. Preserve the balance without inventing prior events.
        sql.exec("INSERT INTO credit_events (at, kind, operation, used, delta, remaining) VALUES (?, 'opening', '', 0, 0, ?)", Date.now(), wallet.balance);
      }
    });
  }

  async fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    const body = request.method === "POST" ? await request.json() as Record<string, unknown> : {};
    const sql = this.ctx.storage.sql;
    if (path === "/credential" && request.method === "GET") {
      return Response.json(sql.exec("SELECT salt, hash FROM credential WHERE id=1").toArray()[0] ?? null);
    }
    return this.ctx.storage.transactionSync(() => {
      const balance = () => sql.exec<{ balance: number }>("SELECT balance FROM wallet WHERE id=1").toArray()[0].balance;
      const event = (kind: string, operation = "", used = 0, delta = 0) => {
        sql.exec("INSERT INTO credit_events (at, kind, operation, used, delta, remaining) VALUES (?, ?, ?, ?, ?, ?)", Date.now(), kind, operation, used, delta, balance());
      };
      const initialize = () => {
        if (!sql.exec("SELECT id FROM wallet WHERE id=1").toArray().length) {
          sql.exec("INSERT INTO wallet VALUES (1, ?)", SIGNUP_CREDITS);
          event("signup", "", 0, SIGNUP_CREDITS);
        }
      };
      if (path === "/throttle") {
        const window = Math.floor(Date.now() / 3600000);
        const row = sql.exec<{ window: number; used: number }>("SELECT window, used FROM throttle WHERE id=1").toArray()[0];
        const used = row?.window === window ? row.used : 0;
        if (used >= 20) return Response.json({ error: "시도 횟수가 많습니다. 나중에 다시 시도하세요." }, { status: 429 });
        sql.exec("INSERT INTO throttle VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET window=excluded.window, used=excluded.used", window, used + 1);
        return Response.json({ ok: true });
      }
      if (path === "/register") {
        if (typeof body.salt !== "string" || typeof body.hash !== "string") return new Response(null, { status: 400 });
        if (sql.exec("SELECT id FROM credential WHERE id=1").toArray().length) return Response.json({ error: "사용할 수 없는 아이디입니다." }, { status: 409 });
        sql.exec("INSERT INTO credential VALUES (1, ?, ?)", body.salt, body.hash);
        initialize();
        return Response.json({ ok: true });
      }
      if (!["/balance", "/history", "/reserve", "/complete", "/release"].includes(path)) return new Response(null, { status: 404 });
      initialize();
      // Provider requests time out in 90 seconds; expired reservations recover after 10 minutes.
      const expired = sql.exec<Reservation>("SELECT id, charged, operation, unlimited FROM ledger WHERE status='reserved' AND expires < ?", Date.now()).toArray();
      for (const pending of expired) {
        sql.exec("UPDATE wallet SET balance=balance+? WHERE id=1", pending.charged);
        sql.exec("UPDATE ledger SET status='released' WHERE id=?", pending.id);
        event("expired", pending.operation, 0, pending.charged);
      }
      if (path === "/balance") return Response.json({ remaining: balance(), unlimited: false });
      if (path === "/history") {
        const cursor = Number(new URL(request.url).searchParams.get("before")) || Number.MAX_SAFE_INTEGER;
        if (!Number.isSafeInteger(cursor) || cursor < 1) return new Response(null, { status: 400 });
        const rows = sql.exec<CreditEvent>("SELECT * FROM credit_events WHERE seq < ? ORDER BY seq DESC LIMIT 51", cursor).toArray();
        return Response.json({ entries: rows.slice(0, 50), nextCursor: rows.length > 50 ? rows[49].seq : null });
      }
      if (typeof body.id !== "string" || !/^[a-zA-Z0-9-]{16,80}$/.test(body.id)) return new Response(null, { status: 400 });
      const row = sql.exec<Reservation>("SELECT * FROM ledger WHERE id=?", body.id).toArray()[0];
      if (path === "/reserve") {
        if (row) return Response.json({ error: "이미 처리 중이거나 처리된 요청입니다." }, { status: 409 });
        if (typeof body.operation !== "string" || !Object.prototype.hasOwnProperty.call(CREDIT_OPERATIONS, body.operation)) return new Response(null, { status: 400 });
        const required = CREDIT_OPERATIONS[body.operation as CreditOperation].cost;
        const charged = body.unlimited === true ? 0 : required;
        if (balance() < charged) return Response.json({ remaining: balance(), required, unlimited: false }, { status: 402 });
        sql.exec("UPDATE wallet SET balance=balance-? WHERE id=1", charged);
        sql.exec("INSERT INTO ledger (id, status, expires, charged, operation, unlimited) VALUES (?, 'reserved', ?, ?, ?, ?)", body.id, Date.now() + 600000, charged, body.operation, body.unlimited === true ? 1 : 0);
        event("reserved", body.operation, 0, -charged);
      } else if (row?.status === "reserved") {
        sql.exec("UPDATE ledger SET status=? WHERE id=?", path === "/complete" ? "spent" : "released", body.id);
        if (path === "/release") {
          sql.exec("UPDATE wallet SET balance=balance+? WHERE id=1", row.charged);
          event("released", row.operation, 0, row.charged);
        } else event(row.unlimited ? "unlimited" : "spent", row.operation, row.charged);
      } else if (!row || (path === "/complete" && row.status !== "spent")) return new Response(null, { status: 409 });
      return Response.json({ remaining: balance(), unlimited: false });
    });
  }
}

export const memberRequest = (namespace: QuotaNamespace | undefined, id: string, path: string, body?: Record<string, unknown>) => {
  if (!namespace) throw new Error("Member storage unavailable");
  return namespace.get(namespace.idFromName(id)).fetch(new Request(`https://member.internal${path}`, {
    method: body ? "POST" : "GET", body: body ? JSON.stringify(body) : undefined,
    headers: { "Content-Type": "application/json" },
  }));
};
