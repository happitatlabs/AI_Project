import { useEffect, useRef, useState } from "react";
import { CREDIT_OPERATIONS, CREDIT_PACKS, type CreditBalance, type CreditOperation } from "./creditPolicy";
import type { CreditEvent } from "./memberAccount";

type HistoryEntry = Omit<CreditEvent, "remaining"> & { remaining: number | null };
const eventLabels: Record<string, string> = {
  signup: "가입 지급", opening: "기존 잔액 이월", reserved: "처리 중 · 예약 차감",
  spent: "사용 확정", unlimited: "무제한 사용", released: "취소·실패 반환", expired: "시간 초과 반환",
};

export function CreditsDialog({ onClose, balance, authenticated, initialTab }: {
  onClose: () => void; balance?: CreditBalance; authenticated: boolean; initialTab: "history" | "packs";
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState(initialTab);
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [packs, setPacks] = useState<typeof CREDIT_PACKS>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const requestNumber = useRef(0);
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    const update = () => setRefresh(value => value + 1);
    window.addEventListener("sql-ai-complete", update);
    return () => window.removeEventListener("sql-ai-complete", update);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const number = ++requestNumber.current;
    setError(""); setLoading(true); setEntries([]); setCursor(null);
    const url = tab === "packs" ? "/api/credits/packs" : "/api/credits/history";
    if (tab === "history" && !authenticated) { setLoading(false); return; }
    void fetch(url, { signal: controller.signal, cache: "no-store" }).then(async response => {
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "Credits 정보를 불러오지 못했습니다.");
      if (number !== requestNumber.current) return;
      if (tab === "packs") setPacks(body.packs);
      else { setEntries(body.entries); setCursor(body.nextCursor); }
    }).catch(e => { if (!controller.signal.aborted && number === requestNumber.current) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted && number === requestNumber.current) setLoading(false); });
    return () => { controller.abort(); requestNumber.current++; };
  }, [tab, authenticated, refresh]);
  const loadMore = async () => {
    if (cursor === null || loading) return;
    const number = ++requestNumber.current;
    setLoading(true); setError("");
    try {
      const response = await fetch(`/api/credits/history?before=${cursor}`, { cache: "no-store" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "사용 이력을 불러오지 못했습니다.");
      if (number === requestNumber.current) { setEntries(previous => [...previous, ...body.entries]); setCursor(body.nextCursor); }
    } catch (e) { if (number === requestNumber.current) setError(e instanceof Error ? e.message : "사용 이력을 불러오지 못했습니다."); }
    finally { if (number === requestNumber.current) setLoading(false); }
  };
  return <dialog ref={dialog} className="member-dialog credits-dialog" onCancel={onClose} aria-labelledby="credits-title">
    <header><h2 id="credits-title">Credits</h2><button type="button" onClick={onClose} aria-label="Credits 닫기">닫기</button></header>
    <p className="credits-dialog-balance">{balance?.unlimited ? "무제한 · 테스트 계정" : authenticated ? `잔여 ${balance?.remaining ?? "확인 중"} Credits` : "무료 가입 시 10 Credits"}</p>
    <div className="credits-tabs" role="tablist" aria-label="Credits 메뉴">
      <button type="button" id="credits-history-tab" role="tab" aria-selected={tab === "history"} aria-controls="credits-history-panel" onClick={() => setTab("history")}>사용 이력</button>
      <button type="button" id="credits-packs-tab" role="tab" aria-selected={tab === "packs"} aria-controls="credits-packs-panel" onClick={() => setTab("packs")}>크레딧 팩</button>
    </div>
    {error ? <p role="alert">{error} <button type="button" onClick={() => setRefresh(value => value + 1)}>다시 시도</button></p> : null}
    {tab === "history" ? <section role="tabpanel" id="credits-history-panel" aria-labelledby="credits-history-tab">
      {!authenticated ? <p>로그인 후 사용 이력을 확인할 수 있습니다.</p> : <>
        <div className="credit-history-scroll"><table className="credit-history-table">
          <thead><tr><th>시간</th><th>작업 / 내역</th><th>사용</th><th>잔액 변동</th><th>잔여</th></tr></thead>
          <tbody>{entries.map(entry => <tr key={entry.seq}>
            <td>{new Date(entry.at).toLocaleString("ko-KR", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
            <td><strong>{CREDIT_OPERATIONS[entry.operation as CreditOperation]?.label ?? (entry.operation === "legacy" ? "기존 AI 요청" : "Credits")}</strong><small>{eventLabels[entry.kind] ?? entry.kind}</small></td>
            <td>{entry.kind === "unlimited" ? "무료" : entry.used}</td>
            <td>{entry.delta > 0 ? "+" : ""}{entry.delta}</td>
            <td>{entry.remaining === null ? "무제한" : entry.remaining}</td>
          </tr>)}</tbody>
        </table></div>
        {!entries.length && !loading && !error ? <p>사용 이력이 없습니다.</p> : null}
        {cursor !== null ? <button type="button" disabled={loading} onClick={() => void loadMore()}>이전 이력 더 보기</button> : null}
      </>}
    </section> : <section role="tabpanel" id="credits-packs-panel" aria-labelledby="credits-packs-tab">
      <div className="credit-packs">{packs.map(pack => <article key={pack.id} className="credit-pack">
        <h3>{pack.credits} Credits</h3><p>가격 미정</p><button type="button" disabled>결제 준비 중</button>
      </article>)}</div>
      <table className="credit-price-table"><caption>AI 작업별 사용량</caption><tbody>{Object.entries(CREDIT_OPERATIONS).map(([id, item]) => <tr key={id}><th>{item.label}</th><td>{item.cost} Credits</td></tr>)}</tbody></table>
    </section>}
    {loading ? <p role="status">불러오는 중</p> : null}
  </dialog>;
}
