import type { QueryPurpose } from "./diagnosisRules";

export type SampleCase = {
  id: string;
  title: string;
  purpose: QueryPurpose;
  columns: string;
  sql: string;
  description: string;
};

const USER_COLUMNS = `user_id
user_nm
dept_cd
use_yn
del_yn
status_cd
reg_dt`;

export const SAMPLE_CASES: SampleCase[] = [
  {
    id: "general-missing-conditions",
    title: "일반 조회: 조건 누락 SQL",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm
FROM tb_user`,
    description:
      "일반 사용자 목록 조회에서 사용 여부, 삭제 여부, 상태, 권한, 기간 조건이 빠진 사례입니다.",
  },
  {
    id: "general-complete-conditions",
    title: "일반 조회: 조건 포함 SQL",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm
FROM tb_user
WHERE use_yn = 'Y'
  AND del_yn = 'N'
  AND status_cd = 'ACTIVE'
  AND dept_cd = :userOrgCode
  AND reg_dt >= :startDate
  AND reg_dt < :endDate`,
    description:
      "일반 조회에서 주요 운영 조건과 권한, 기간 조건을 모두 포함한 사례입니다.",
  },
  {
    id: "statistics-summary",
    title: "통계 조회",
    purpose: "STATISTICS",
    columns: `dept_cd
status_cd
use_yn
del_yn
reg_dt
user_id`,
    sql: `SELECT dept_cd, COUNT(*) AS user_count
FROM tb_user
GROUP BY dept_cd`,
    description:
      "통계 목적에서는 조건 누락을 오류로 단정하지 않고 집계 기준 검토 항목으로 안내하는 사례입니다.",
  },
  {
    id: "admin-search",
    title: "관리자 조회",
    purpose: "ADMIN",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm, status_cd, use_yn, del_yn
FROM tb_user
WHERE use_yn IN ('Y', 'N')
  AND del_yn IN ('Y', 'N')`,
    description:
      "관리자 화면에서 비활성 또는 삭제 데이터는 의도적으로 포함하지만 기관 권한 조건이 빠진 사례입니다.",
  },
  {
    id: "history-search",
    title: "이력 조회",
    purpose: "HISTORY",
    columns: `hist_id
user_id
status_cd
dept_cd
use_yn
created_at`,
    sql: `SELECT hist_id, user_id, status_cd, created_at
FROM tb_user_history
WHERE dept_cd = :userOrgCode`,
    description:
      "이력 조회에서 권한 조건은 있으나 상태와 기간 조건 검토가 필요한 사례입니다.",
  },
  {
    id: "batch-target",
    title: "배치 작업",
    purpose: "BATCH",
    columns: `user_id
dept_cd
org_cd
use_yn
delete_yn
stts_cd
created_at`,
    sql: `SELECT user_id, dept_cd, org_cd
FROM tb_user
WHERE user_id IS NOT NULL`,
    description:
      "배치 작업에서는 누락 가능 조건을 모두 info 수준으로만 검토하는 사례입니다.",
  },
  {
    id: "select-star-performance",
    title: "SELECT * 개선 샘플",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `select *
from tb_user
where use_yn='Y'`,
    description:
      "SELECT *를 입력된 컬럼 목록 기반 명시 컬럼 후보로 바꿔볼 수 있는 사례입니다.",
  },
  {
    id: "use-delete-condition-reinforce",
    title: "use_yn/del_yn 조건 보강 샘플",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm
FROM tb_user
WHERE dept_cd = :userOrgCode`,
    description:
      "일반 조회에서 use_yn, del_yn, status_cd 조건 보강 후보가 생성되는 사례입니다.",
  },
  {
    id: "date-function-performance",
    title: "날짜 함수 성능 개선 샘플",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm
FROM tb_user
WHERE TO_CHAR(reg_dt, 'YYYY-MM-DD') = '2026-06-03'
  AND use_yn = 'Y'
  AND del_yn = 'N'`,
    description:
      "날짜 컬럼 함수 조건을 범위 조건 후보로 검토할 수 있는 사례입니다.",
  },
  {
    id: "leading-wildcard-like",
    title: "LIKE '%검색어%' 주의 샘플",
    purpose: "GENERAL",
    columns: USER_COLUMNS,
    sql: `SELECT user_id, user_nm
FROM tb_user
WHERE user_nm LIKE '%홍길동%'
  AND use_yn = 'Y'
  AND del_yn = 'N'`,
    description:
      "앞쪽 와일드카드 LIKE 검색이 인덱스 사용에 불리할 수 있음을 안내하는 사례입니다.",
  },
  {
    id: "complex-sql-limited-auto-change",
    title: "복잡한 SQL 자동 변경 제한 샘플",
    purpose: "STATISTICS",
    columns: `dept_cd
org_cd
user_id
use_yn
del_yn
status_cd
reg_dt`,
    sql: `WITH base_user AS (
  SELECT u.user_id, u.dept_cd, u.status_cd, d.org_cd
  FROM tb_user u
  JOIN tb_dept d ON u.dept_cd = d.dept_cd
  JOIN tb_org o ON d.org_cd = o.org_cd
  WHERE u.reg_dt >= :startDate
)
SELECT org_cd, status_cd, COUNT(*) AS user_count
FROM base_user
GROUP BY org_cd, status_cd`,
    description:
      "WITH, JOIN 2개 이상, GROUP BY가 포함되어 자동 조건/성능 변경을 제한하는 사례입니다.",
  },
];
