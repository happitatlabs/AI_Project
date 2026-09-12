import type { QuotaNamespace } from "./demoQuota.js";

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
  }

  async fetch(request: Request): Promise<Response> {
    const path = new URL(request.url).pathname;
    const body = request.method === "POST" ? await request.json() as Record<string, unknown> : {};
    const sql = this.ctx.storage.sql;
    if (path === "/credential" && request.method === "GET") {
      return Response.json(sql.exec("SELECT salt, hash FROM credential WHERE id=1").toArray()[0] ?? null);
    }
    return this.ctx.storage.transactionSync(() => {
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
        sql.exec("INSERT OR IGNORE INTO wallet VALUES (1, 1)");
        return Response.json({ ok: true });
      }
      if (!["/balance", "/reserve", "/complete", "/release"].includes(path)) return new Response(null, { status: 404 });
      sql.exec("INSERT OR IGNORE INTO wallet VALUES (1, 1)");
      // Provider requests time out in 90 seconds; expired reservations recover after 10 minutes.
      const expired = sql.exec<{ id: string }>("SELECT id FROM ledger WHERE status='reserved' AND expires < ?", Date.now()).toArray();
      if (expired.length) {
        sql.exec("UPDATE wallet SET balance=balance+? WHERE id=1", expired.length);
        sql.exec("UPDATE ledger SET status='released' WHERE status='reserved' AND expires < ?", Date.now());
      }
      const balance = () => sql.exec<{ balance: number }>("SELECT balance FROM wallet WHERE id=1").toArray()[0].balance;
      if (path === "/balance") return Response.json({ remaining: balance(), unlimited: false });
      if (typeof body.id !== "string" || !/^[a-zA-Z0-9-]{16,80}$/.test(body.id)) return new Response(null, { status: 400 });
      const row = sql.exec<{ status: string }>("SELECT status FROM ledger WHERE id=?", body.id).toArray()[0];
      if (path === "/reserve") {
        if (row) return Response.json({ error: "이미 처리 중이거나 처리된 요청입니다." }, { status: 409 });
        if (!balance()) return Response.json({ remaining: 0, unlimited: false }, { status: 402 });
        sql.exec("UPDATE wallet SET balance=balance-1 WHERE id=1");
        sql.exec("INSERT INTO ledger VALUES (?, 'reserved', ?)", body.id, Date.now() + 600000);
      } else if (row?.status === "reserved") {
        sql.exec("UPDATE ledger SET status=? WHERE id=?", path === "/complete" ? "spent" : "released", body.id);
        if (path === "/release") sql.exec("UPDATE wallet SET balance=balance+1 WHERE id=1");
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
