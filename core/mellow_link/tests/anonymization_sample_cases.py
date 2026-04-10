from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from mellow_link.modules.rebuild_assistant.service import RebuildAssistantService
from mellow_link.services.anonymization import (
    AnonymizationRunRequest,
    AnonymizationService,
    AnonymizationStorage,
    build_debug_anonymization_report_from_bundle,
)
from mellow_link.services.anonymization.schemas import (
    AnonymizationAsset,
    MaskingLevel,
    SafeAnalysisBundle,
)


BundleMutator = Callable[[SafeAnalysisBundle], None]


@dataclass(frozen=True)
class SampleAssetInput:
    name: str
    content: str
    language: str = ""
    kind_hint: str = ""


@dataclass(frozen=True)
class SampleExpectation:
    validation_passed: bool
    preview_visible: bool
    min_total_replacements: int = 0
    max_total_replacements: int | None = None
    required_risk_flags: tuple[str, ...] = ()
    required_findings: tuple[str, ...] = ()
    canonical_must_include: tuple[str, ...] = ()
    canonical_must_exclude: tuple[str, ...] = ()
    preview_must_include: tuple[str, ...] = ()
    preview_must_exclude: tuple[str, ...] = ()
    required_prepared_sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class AnonymizationSampleCase:
    sample_name: str
    purpose: str
    input_summary: str
    included_asset_kinds: tuple[str, ...]
    core_patterns: tuple[str, ...]
    assets: tuple[SampleAssetInput, ...]
    expectation: SampleExpectation
    candidate_test_files: tuple[str, ...]
    mutate_bundle: BundleMutator | None = None


@dataclass(frozen=True)
class ExecutedAnonymizationSample:
    case: AnonymizationSampleCase
    request: AnonymizationRunRequest
    safe_bundle: SafeAnalysisBundle
    report: dict
    prepared_source_code: str
    prepared_sql_queries: str
    prepared_ui_template: str
    prepared_framework_info: str


def _mark_bundle_guard_mapping(bundle: SafeAnalysisBundle) -> None:
    bundle.guard.contains_mapping = True


NORMAL_BALANCED_BUNDLE = AnonymizationSampleCase(
    sample_name="normal_balanced_bundle",
    purpose="익명화 정상 적용, validation pass, preview 노출, SafeAnalysisBundle 소비 입력 구성이 모두 채워지는 기본 계약을 검증한다.",
    input_summary="source/sql/ui/framework 자산을 모두 포함하고, 구조 식별자와 일부 민감 문자열이 섞인 일반적인 현대화 입력.",
    included_asset_kinds=("source_code", "sql_queries", "ui_template", "framework_info"),
    core_patterns=(
        "class OrderClosureService",
        "def submit_order(order_data, retry_flag, note_text)",
        "FROM legacy_orders",
        "JOIN customer_profile",
        "action=\"/orders/submit\"",
        "ops.order@example.com",
    ),
    assets=(
        SampleAssetInput(
            name="order_service.py",
            language="python",
            content="""
class OrderClosureService:
    def submit_order(order_data, retry_flag, note_text):
        api_base = "/internal/orders/submit"
        owner_email = "ops.order@example.com"
        if retry_flag:
            return order_data
        return fetch_summary(order_data, note_text, owner_email)
""".strip(),
        ),
        SampleAssetInput(
            name="order_lookup.sql",
            language="sql",
            content="""
SELECT o.order_id, o.status_code, o.memo_text
FROM legacy_orders o
JOIN customer_profile p ON p.customer_id = o.customer_id
WHERE o.status_code = 'READY'
  AND p.contact_email = 'ops.order@example.com'
""".strip(),
        ),
        SampleAssetInput(
            name="legacy_order.jsp",
            language="jsp",
            content="""
<%@ page language="java" %>
<form action="/orders/submit" method="post">
  <c:if test="${not empty helperText}">
    <span>${helperText}</span>
  </c:if>
</form>
""".strip(),
        ),
        SampleAssetInput(
            name="pom.xml",
            language="xml",
            content="""
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip(),
        ),
    ),
    expectation=SampleExpectation(
        validation_passed=True,
        preview_visible=True,
        min_total_replacements=22,
        max_total_replacements=24,
        canonical_must_include=("order_data", "retry_flag", "note_text", "helperText"),
        canonical_must_exclude=("OrderClosureService", "submit_order", "legacy_orders", "customer_profile", "/orders/submit"),
        preview_must_include=("[CLASS]", "[FUNCTION]", "[TABLE]", "[API]"),
        preview_must_exclude=("OrderClosureService", "submit_order", "ops.order@example.com", "/internal/orders/submit"),
        required_prepared_sections=("source_code", "sql_queries", "ui_template", "framework_info"),
    ),
    candidate_test_files=("core/mellow_link/tests/test_anonymization_sample_cases.py",),
)


AMBIGUOUS_IDENTIFIER_RETENTION = AnonymizationSampleCase(
    sample_name="ambiguous_identifier_retention",
    purpose="고신뢰 구조 식별자는 일부만 치환하고, data/mode/helperFlag 같은 애매한 식별자는 canonical 쪽에서 유지되는지 검증한다.",
    input_summary="일반 변수명, 느슨한 노트, 부분 SQL이 섞여 있고 고신뢰 패턴은 function/table 정도만 소량 포함된 입력.",
    included_asset_kinds=("source_code", "notes", "sql_queries"),
    core_patterns=(
        "function renderPanel(data, mode, helperFlag)",
        "Draft words that should stay readable in canonical form",
        "FROM draft_queue",
    ),
    assets=(
        SampleAssetInput(
            name="render_helper.js",
            language="javascript",
            content="""
function renderPanel(data, mode, helperFlag) {
  if (helperFlag) return previewCard(data, mode);
  return previewCard(mode, data);
}
""".strip(),
        ),
        SampleAssetInput(
            name="operator_notes.md",
            language="markdown",
            content="""
Draft words that should stay readable in canonical form:
data mode helperFlag rowValue nextItem
These are notes, not schema names or API paths.
""".strip(),
        ),
        SampleAssetInput(
            name="draft_queue.sql",
            language="sql",
            content="""
SELECT status_text
FROM draft_queue
WHERE note_text LIKE '%hold%'
""".strip(),
        ),
    ),
    expectation=SampleExpectation(
        validation_passed=True,
        preview_visible=True,
        min_total_replacements=2,
        max_total_replacements=3,
        canonical_must_include=("data", "mode", "helperFlag", "rowValue", "nextItem"),
        canonical_must_exclude=("renderPanel", "draft_queue"),
        preview_must_include=("function", "return", "SELECT", "FROM"),
        preview_must_exclude=("renderPanel", "draft_queue"),
    ),
    candidate_test_files=("core/mellow_link/tests/test_anonymization_sample_cases.py",),
)


SENSITIVE_SIGNAL_HEAVY_BUNDLE = AnonymizationSampleCase(
    sample_name="sensitive_signal_heavy_bundle",
    purpose="민감 문자열이 많이 섞여 있어도 preview는 더 강하게 가려지고, summary.total_replacements는 구조 식별자 기준으로만 집계되는 현재 계약을 검증한다.",
    input_summary="이메일/전화/호스트/내부경로/token 문자열이 source/sql/text에 다수 포함되며, 테이블/컬럼/API path도 함께 등장하는 입력.",
    included_asset_kinds=("source_code", "sql_queries", "notes", "framework_info"),
    core_patterns=(
        "https://legacy-admin.internal.example.com/api/v2/billing/sync",
        "sk_live_1234567890abcdef",
        "/srv/legacy/private/customer_exports",
        "ops-team@corp.local",
        "UPDATE customer_account",
        "JOIN customer_server",
    ),
    assets=(
        SampleAssetInput(
            name="billing_service.py",
            language="python",
            content="""
class CustomerBillingService:
    def sync_customer_account(account_payload, retry_token):
        api_base = "https://legacy-admin.internal.example.com/api/v2/billing/sync"
        secret_value = "sk_live_1234567890abcdef"
        archive_path = "/srv/legacy/private/customer_exports"
        contact_email = "ops-team@corp.local"
        phone_note = "010-5555-1111"
        return post_request(api_base, account_payload, retry_token, contact_email, phone_note)
""".strip(),
        ),
        SampleAssetInput(
            name="customer_merge.sql",
            language="sql",
            content="""
UPDATE customer_account
SET sync_status = 'READY',
    secret_ref = 'vault://finance/prod/customer-sync',
    support_phone = '02-555-9988'
WHERE contact_email = 'ops-team@corp.local'
  AND api_endpoint = 'https://legacy-admin.internal.example.com/api/v2/billing/sync';

INSERT INTO billing_audit_log (account_id, raw_payload)
SELECT a.account_id, a.raw_payload
FROM customer_account a
JOIN customer_server b ON b.account_id = a.account_id
WHERE b.host_name = 'billing-db.internal.example.com';
""".strip(),
        ),
        SampleAssetInput(
            name="incident_note.txt",
            language="text",
            content="""
Operator note: primary contact ops-team@corp.local, backup phone "010-4444-2222".
Escalate on host "db-billing.internal.example.com" and file "/srv/legacy/private/customer_exports/report.csv".
Temporary token "tok_live_sensitive_123" must not reach preview.
""".strip(),
        ),
        SampleAssetInput(
            name="pom.xml",
            language="xml",
            content="""
<project>
  <dependencies>
    <dependency>
      <groupId>org.mybatis.spring.boot</groupId>
      <artifactId>mybatis-spring-boot-starter</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip(),
        ),
    ),
    expectation=SampleExpectation(
        validation_passed=True,
        preview_visible=True,
        min_total_replacements=26,
        max_total_replacements=28,
        canonical_must_include=("ops-team@corp.local", "sk_live_1234567890abcdef", "db-billing.internal.example.com"),
        canonical_must_exclude=("CustomerBillingService", "sync_customer_account", "customer_account", "customer_server"),
        preview_must_include=("[CLASS]", "[FUNCTION]", "[TABLE]", "[COLUMN]", "[API]"),
        preview_must_exclude=(
            "legacy-admin.internal.example.com",
            "ops-team@corp.local",
            "sk_live_1234567890abcdef",
            "010-4444-2222",
            "/srv/legacy/private/customer_exports",
            "tok_live_sensitive_123",
        ),
    ),
    candidate_test_files=("core/mellow_link/tests/test_anonymization_sample_cases.py",),
)


FAILURE_GUARD_MAPPING_VISIBLE = AnonymizationSampleCase(
    sample_name="failure_guard_mapping_visible",
    purpose="safe bundle guard 계약을 일부러 깨뜨려 validation fail, preview 차단, findings/risk_flags 생성이 유지되는지 검증한다.",
    input_summary="일반 source/sql 입력을 만든 뒤 safe bundle guard.contains_mapping 을 강제로 true 로 바꿔 preview 노출 차단 경로를 유도한다.",
    included_asset_kinds=("source_code", "sql_queries", "mutated_bundle"),
    core_patterns=(
        "class UnsafePreviewBridge",
        "def expose_mapping(debug_token)",
        "route = \"/debug/raw\"",
        "FROM mapping_audit",
    ),
    assets=(
        SampleAssetInput(
            name="unsafe_preview_bridge.py",
            language="python",
            content="""
class UnsafePreviewBridge:
    def expose_mapping(debug_token):
        route = "/debug/raw"
        return debug_token
""".strip(),
        ),
        SampleAssetInput(
            name="mapping_audit.sql",
            language="sql",
            content="""
SELECT raw_token
FROM mapping_audit
WHERE raw_token = 'tok_debug_only'
""".strip(),
        ),
    ),
    expectation=SampleExpectation(
        validation_passed=False,
        preview_visible=False,
        min_total_replacements=5,
        max_total_replacements=7,
        required_risk_flags=("guard_contains_mapping",),
        required_findings=("guard_contains_mapping",),
        canonical_must_include=("debug_token", "tok_debug_only"),
        canonical_must_exclude=("UnsafePreviewBridge", "expose_mapping", "mapping_audit", "/debug/raw", "raw_token"),
    ),
    candidate_test_files=("core/mellow_link/tests/test_anonymization_sample_cases.py",),
    mutate_bundle=_mark_bundle_guard_mapping,
)


EVENT_STREAM_SPLIT_CONTRACT = AnonymizationSampleCase(
    sample_name="event_stream_split_contract",
    purpose="동일 익명화 결과에서 user snapshot 은 summary 만 가지며 debug report 는 admin/dev surface 에서만 보이는지 검증한다.",
    input_summary="summary/debug report 를 모두 생성할 수 있는 일반 source/sql/ui/framework 입력.",
    included_asset_kinds=("source_code", "sql_queries", "ui_template", "framework_info"),
    core_patterns=(
        "class AccountController",
        "def load_account(account_id, view_mode)",
        "FROM customer_account",
        "action=\"/accounts/detail\"",
    ),
    assets=(
        SampleAssetInput(
            name="account_controller.py",
            language="python",
            content="""
class AccountController:
    def load_account(account_id, view_mode):
        route_path = "/api/accounts/detail"
        return render_account(account_id, view_mode, route_path)
""".strip(),
        ),
        SampleAssetInput(
            name="account_lookup.sql",
            language="sql",
            content="""
SELECT a.account_name
FROM customer_account a
WHERE a.account_id = :account_id
""".strip(),
        ),
        SampleAssetInput(
            name="account_detail.jsp",
            language="jsp",
            content="""
<form action="/accounts/detail" method="get">
  <input name="viewMode" value="${viewMode}" />
</form>
""".strip(),
        ),
        SampleAssetInput(
            name="pom.xml",
            language="xml",
            content="""
<project>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
  </dependencies>
</project>
""".strip(),
        ),
    ),
    expectation=SampleExpectation(
        validation_passed=True,
        preview_visible=True,
        min_total_replacements=16,
        max_total_replacements=18,
        canonical_must_include=("account_id", "view_mode", "viewMode"),
        canonical_must_exclude=("AccountController", "load_account", "customer_account", "/accounts/detail"),
        preview_must_include=("[CLASS]", "[FUNCTION]", "[TABLE]", "[API]"),
        preview_must_exclude=("AccountController", "load_account", "/api/accounts/detail"),
        required_prepared_sections=("source_code", "sql_queries", "ui_template", "framework_info"),
    ),
    candidate_test_files=("core/mellow_link/tests/test_anonymization_sample_cases.py",),
)


ANONYMIZATION_SAMPLE_CASES: tuple[AnonymizationSampleCase, ...] = (
    NORMAL_BALANCED_BUNDLE,
    AMBIGUOUS_IDENTIFIER_RETENTION,
    SENSITIVE_SIGNAL_HEAVY_BUNDLE,
    FAILURE_GUARD_MAPPING_VISIBLE,
    EVENT_STREAM_SPLIT_CONTRACT,
)

SERVICE_BACKED_SAMPLE_CASES: tuple[AnonymizationSampleCase, ...] = ANONYMIZATION_SAMPLE_CASES

ANONYMIZATION_SAMPLE_CASES_BY_NAME = {
    case.sample_name: case for case in ANONYMIZATION_SAMPLE_CASES
}


def build_run_request(case: AnonymizationSampleCase) -> AnonymizationRunRequest:
    assets = []
    for index, asset in enumerate(case.assets, start=1):
        text = asset.content.strip()
        assets.append(
            AnonymizationAsset(
                asset_id=f"asset_{index:03d}",
                name=asset.name,
                temp_file_id=f"temp_{index:03d}",
                size=len(text.encode("utf-8")),
                kind_hint=asset.kind_hint,
                language=asset.language,
                content_text=text,
                original_bytes=text.encode("utf-8"),
            )
        )
    return AnonymizationRunRequest(
        project_id=f"proj_{case.sample_name}",
        upload_session_id=f"upload_{case.sample_name}",
        masking_level=MaskingLevel.FULL,
        assets=assets,
    )


def execute_sample_case(case: AnonymizationSampleCase, *, tmp_path: Path) -> ExecutedAnonymizationSample:
    request = build_run_request(case)
    storage = AnonymizationStorage(root=tmp_path / case.sample_name)
    service = AnonymizationService(storage=storage)
    result = service.run_anonymization_pipeline(request)
    bundle = result.safe_bundle
    if case.mutate_bundle is not None:
        case.mutate_bundle(bundle)
    report = build_debug_anonymization_report_from_bundle(bundle)
    prepared = RebuildAssistantService().prepare_safe_bundle_input(
        goal=f"{case.sample_name} safe bundle verification",
        safe_bundle=bundle,
        constraints=["sample_contract"],
    )
    return ExecutedAnonymizationSample(
        case=case,
        request=request,
        safe_bundle=bundle,
        report=report,
        prepared_source_code=prepared.assets.source_code,
        prepared_sql_queries=prepared.assets.sql_queries,
        prepared_ui_template=prepared.assets.ui_template,
        prepared_framework_info=prepared.assets.framework_info,
    )
