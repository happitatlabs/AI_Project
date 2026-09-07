import { useMemo, useState } from "react";
import {
  buildSqlChangeReview,
  buildSqlChangeReviewMarkdown,
  type SqlChangeReviewResult,
} from "./sqlChangeReview";
import { SQL_CHANGE_REVIEW_CASES } from "./sqlChangeReviewCases";

type CopyStatus = "idle" | "copied" | "failed";

const copyText = async (value: string) => {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
};

const DEFAULT_CASE = SQL_CHANGE_REVIEW_CASES[0];

const initialReview = () => buildSqlChangeReview(DEFAULT_CASE.beforeSql, DEFAULT_CASE.afterSql);

export function SqlChangeReviewWorkspace() {
  const [selectedCaseId, setSelectedCaseId] = useState(DEFAULT_CASE.id);
  const [beforeSql, setBeforeSql] = useState(DEFAULT_CASE.beforeSql);
  const [afterSql, setAfterSql] = useState(DEFAULT_CASE.afterSql);
  const [review, setReview] = useState<SqlChangeReviewResult | undefined>(() => initialReview());
  const [errorMessage, setErrorMessage] = useState("");
  const [checkedItems, setCheckedItems] = useState<string[]>([]);
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const completedCount = checkedItems.length;
  const checklistCount = review?.checklist.length ?? 0;
  const progress = checklistCount > 0 ? Math.round((completedCount / checklistCount) * 100) : 0;
  const markdown = useMemo(
    () => review ? buildSqlChangeReviewMarkdown(review) : "",
    [review],
  );

  const invalidateReview = () => {
    setReview(undefined);
    setCheckedItems([]);
    setCopyStatus("idle");
    setErrorMessage("");
  };

  const updateBeforeSql = (value: string) => {
    setBeforeSql(value);
    invalidateReview();
  };

  const updateAfterSql = (value: string) => {
    setAfterSql(value);
    invalidateReview();
  };

  const runReview = () => {
    try {
      const nextReview = buildSqlChangeReview(beforeSql, afterSql);
      setReview(nextReview);
      setCheckedItems([]);
      setCopyStatus("idle");
      setErrorMessage("");
    } catch (error) {
      setReview(undefined);
      setErrorMessage(error instanceof Error ? error.message : "SQL 변경 비교에 실패했습니다.");
    }
  };

  const loadCase = (caseId: string) => {
    const selectedCase = SQL_CHANGE_REVIEW_CASES.find((candidate) => candidate.id === caseId) ?? DEFAULT_CASE;

    setSelectedCaseId(selectedCase.id);
    setBeforeSql(selectedCase.beforeSql);
    setAfterSql(selectedCase.afterSql);
    setReview(buildSqlChangeReview(selectedCase.beforeSql, selectedCase.afterSql));
    setCheckedItems([]);
    setCopyStatus("idle");
    setErrorMessage("");
  };

  const selectedCase = SQL_CHANGE_REVIEW_CASES.find((candidate) => candidate.id === selectedCaseId) ?? DEFAULT_CASE;

  const toggleChecklistItem = (id: string) => {
    setCheckedItems((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    );
  };

  const copyReview = async () => {
    setCopyStatus(await copyText(markdown) ? "copied" : "failed");
  };

  return (
    <section className="change-review-workspace">
      <header className="change-review-intro">
        <div>
          <p className="section-kicker">변경 전 검토</p>
          <h2>수정 전후 SQL에서 달라진 구조와 확인할 항목을 비교합니다.</h2>
          <p>
            SQL을 실행하지 않고 테이블, JOIN, 조건, 집계, 쓰기 대상과 새 리스크를 비교합니다.
          </p>
        </div>
        <span className="analysis-boundary">SQL 실행 없음</span>
      </header>

      <div className="change-input-toolbar">
        <label className="change-case-picker" htmlFor="change-review-case">
          <span>대표 검증 사례</span>
          <select
            id="change-review-case"
            value={selectedCaseId}
            onChange={(event) => loadCase(event.target.value)}
          >
            {SQL_CHANGE_REVIEW_CASES.map((reviewCase) => (
              <option key={reviewCase.id} value={reviewCase.id}>{reviewCase.label}</option>
            ))}
          </select>
          <small>{selectedCase.description}</small>
        </label>
        <button className="secondary-button" type="button" onClick={() => loadCase(selectedCaseId)}>
          선택 사례 복원
        </button>
      </div>

      <div className="change-input-grid">
        <section className="change-sql-panel">
          <label htmlFor="before-sql-input">
            <strong>변경 전 SQL</strong>
            <span>현재 운영 또는 수정 전 기준</span>
          </label>
          <textarea
            id="before-sql-input"
            value={beforeSql}
            onChange={(event) => updateBeforeSql(event.target.value)}
            spellCheck={false}
          />
        </section>
        <section className="change-sql-panel">
          <label htmlFor="after-sql-input">
            <strong>변경 후 SQL</strong>
            <span>배포하거나 검토할 변경안</span>
          </label>
          <textarea
            id="after-sql-input"
            value={afterSql}
            onChange={(event) => updateAfterSql(event.target.value)}
            spellCheck={false}
          />
        </section>
      </div>

      <div className="action-row change-review-actions">
        <button
          className="primary-button"
          type="button"
          disabled={!beforeSql.trim() || !afterSql.trim()}
          onClick={runReview}
        >
          변경 구조 비교
        </button>
        <span>비교 결과와 검토 체크리스트는 AI 없이 생성됩니다.</span>
      </div>

      {errorMessage ? <p className="change-review-error" role="alert">{errorMessage}</p> : null}

      {review ? (
        <section className={`change-review-result ${review.severity}`} aria-live="polite">
          <header className="change-result-header">
            <div>
              <p className="section-kicker">룰 기반 변경 검토</p>
              <h2>변경 검토 결과</h2>
              <p>{review.summary}</p>
            </div>
            <div className="change-result-meta" aria-label="변경 요약">
              <span className={`change-severity ${review.severity}`}>
                {review.severity === "critical"
                  ? "우선 확인"
                  : review.severity === "warning"
                    ? "주의"
                    : review.severity === "notice"
                      ? "변경 있음"
                      : "구조 동일"}
              </span>
              <span>{review.operation.before} → {review.operation.after}</span>
            </div>
          </header>

          <section className="change-result-section">
            <div className="section-heading-row">
              <div>
                <p className="section-kicker">핵심 결과</p>
                <h3>먼저 확인할 변경</h3>
              </div>
              <span>상위 {review.keyChanges.length}개</span>
            </div>
            <div className="change-finding-list">
              {review.keyChanges.map((finding, index) => (
                <article className={`change-finding ${finding.severity}`} key={finding.id}>
                  <span className="change-finding-index">{index + 1}</span>
                  <div>
                    <strong>{finding.label}</strong>
                    <p>{finding.statement}</p>
                    <small>{finding.whyItMatters}</small>
                    <details className="finding-evidence">
                      <summary>판단 근거 {finding.evidence.length}개</summary>
                      <ul>
                        {finding.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
                      </ul>
                    </details>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="change-result-section change-so-what">
            <p className="section-kicker">그래서 무엇이 중요한가</p>
            <p>{review.soWhat}</p>
          </section>

          <section className="change-result-section">
            <div className="section-heading-row">
              <div>
                <p className="section-kicker">다음 질문</p>
                <h3>배포 전에 답해야 할 질문</h3>
              </div>
            </div>
            <ol className="change-question-list">
              {review.nextQuestions.map((question) => (
                <li key={question.id}>
                  <strong>{question.question}</strong>
                  <span>{question.reason}</span>
                </li>
              ))}
            </ol>
          </section>

          <section className="change-result-section review-checklist-section">
            <div className="checklist-header">
              <div>
                <p className="section-kicker">검토 기록</p>
                <h3>변경 전 체크리스트</h3>
              </div>
              <strong>{completedCount}/{checklistCount} 확인</strong>
            </div>
            <div
              className="checklist-progress"
              role="progressbar"
              aria-label="변경 검토 진행률"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <span style={{ width: `${progress}%` }} />
            </div>
            <div className="review-checklist">
              {review.checklist.map((item) => (
                <label className={checkedItems.includes(item.id) ? "checked" : ""} key={item.id}>
                  <input
                    type="checkbox"
                    checked={checkedItems.includes(item.id)}
                    onChange={() => toggleChecklistItem(item.id)}
                  />
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.reason}</small>
                  </span>
                </label>
              ))}
            </div>
          </section>

          <details className="change-detail-section">
            <summary>
              <span>구조 변경 상세</span>
              <small>추가·제거된 테이블, JOIN, 조건, 집계 구조</small>
            </summary>
            <div className="change-group-list">
              {review.changeGroups.map((group) => (
                <section key={group.id}>
                  <h3>{group.label}</h3>
                  {group.added.length === 0 && group.removed.length === 0 ? (
                    <p>차이 없음</p>
                  ) : (
                    <div className="change-values">
                      <div>
                        <strong>제거</strong>
                        {group.removed.length > 0 ? (
                          <ul>{group.removed.map((item) => <li key={item}>{item}</li>)}</ul>
                        ) : <p>없음</p>}
                      </div>
                      <div>
                        <strong>추가</strong>
                        {group.added.length > 0 ? (
                          <ul>{group.added.map((item) => <li key={item}>{item}</li>)}</ul>
                        ) : <p>없음</p>}
                      </div>
                    </div>
                  )}
                </section>
              ))}
            </div>
          </details>

          <details className="change-detail-section">
            <summary>
              <span>분석 한계와 주의 사항</span>
              <small>실행 데이터 없이 판단할 수 없는 범위</small>
            </summary>
            <ul className="change-warning-list">
              {review.warnings.map((warning) => <li key={warning}>{warning}</li>)}
            </ul>
          </details>

          <footer className="change-result-footer">
            <p>확인 결과를 변경 요청서나 리뷰 문서에 남길 수 있습니다.</p>
            <button className="secondary-button" type="button" onClick={() => void copyReview()}>
              {copyStatus === "copied" ? "검토 메모 복사됨" : copyStatus === "failed" ? "복사 실패" : "검토 메모 복사"}
            </button>
          </footer>
        </section>
      ) : (
        <section className="change-review-empty">
          <strong>변경 전후 SQL을 비교하면 검토 결과가 여기에 표시됩니다.</strong>
          <span>입력 중에는 이전 비교 결과를 숨겨 잘못된 결과를 보지 않도록 합니다.</span>
        </section>
      )}
    </section>
  );
}
