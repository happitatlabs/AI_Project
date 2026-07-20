# Delivery Package Manifest Contract

- 문서 상태: Implementation contract
- 출력 계약: ZIP archive와 `manifest.json`

## Package 형식

초기 외부 납품 package는 ZIP archive다. archive root에는 `manifest.json`과 allowlist를 통과한 외부 artifact만 둔다. 디렉터리 depth는 고정하며 사용자 입력으로 entry path를 만들지 않는다.

권장 결정적 entry 이름:

```text
manifest.json
report/pilot-report.docx
support/delivery-note.txt
```

`delivery-note.txt`는 optional이며 안전한 bounded metadata로 생성된 경우에만 포함한다. one-page summary와 provenance가 보고서 내부 section이면 별도 파일을 중복 생성하지 않고 manifest의 logical coverage에 기록한다.

## Manifest version

Canonical schema identifier는 `delivery-manifest-v1`이다. 알 수 없는 major version을 조용히 읽지 않는다.

## Manifest 필드

| 필드 | 규칙 |
| --- | --- |
| `manifest_version` | `delivery-manifest-v1` |
| `package_id` | opaque identifier |
| `pilot_ref` | 외부 안전 reference. 내부 Pilot/DB key 미노출 |
| `created_at` | timezone-aware UTC instant |
| `created_by_ref` | opaque operator reference |
| `source_pilot_version` | assembly에 고정한 Priority 2 version |
| `checklist_template_version` | checklist template version |
| `checklist_version` | assembly에 고정한 instance version |
| `artifact_set_fingerprint` | 정렬된 input fingerprint digest |
| `package_checksum` | 완성 archive의 checksum은 package record에 저장하고 self-referential manifest에서는 제외하거나 명시적 `null` 정책 사용 |
| `artifacts` | 아래 ArtifactEntry 목록 |
| `logical_coverage` | `one_page_summary`, `external_provenance` 등 구조 검증 결과 code |
| `assembly_status` | 완성 manifest에서는 `assembled`만 허용 |

### ArtifactEntry

| 필드 | 규칙 |
| --- | --- |
| `artifact_type` | allowlist enum |
| `entry_name` | 안전한 POSIX relative path |
| `byte_size` | 0 이상의 실제 entry size |
| `checksum_algorithm` | 초기값 `sha256` |
| `checksum` | entry bytes의 lowercase hex digest |
| `content_type` | 검증된 allowlist MIME |
| `source_fingerprint` | 내부 경로 없이 source snapshot을 재현하는 digest |

## 안전한 파일명 규칙

- 절대 경로, drive letter, UNC, `..`, 빈 segment, backslash, NUL, 제어문자를 거부한다.
- entry 이름은 service의 고정 mapping에서만 선택한다.
- 원본 파일명과 고객 입력 filename을 package entry에 재사용하지 않는다.
- 대소문자 정규화 후 entry 이름 중복을 거부한다.
- symbolic link, hard link, device entry는 생성하지 않는다.

## Artifact 검증

- source는 기존 project/run archive resolver가 반환한 allowlisted artifact reference만 사용한다.
- canonical resolved path가 허용된 archive root 안에 있어야 하며 symlink component가 있으면 거부한다.
- content type, magic signature, open/reopen 가능성, 개별 size와 총 package size 정책을 검증한다.
- checksum은 bytes를 ZIP에 쓰기 직전에 계산하고 완성 후 entry를 다시 읽어 검증한다.
- 예상하지 않은 artifact type은 `invalid_artifact`로 차단한다.

## 포함 금지 정보

- 내부 절대/상대 저장 경로
- 로컬 사용자명이나 테스트 실행 경로
- 원본 filename
- raw report text를 manifest field로 복제한 값
- SafeAnalysisBundle 등 민감한 bundle identifier
- DB primary key, secret, token, credential
- 실제 이메일, 전화번호 또는 고객 개인정보
- waiver reason 원문 및 내부 exception 문자열

## 결정성과 무결성

- artifact는 `entry_name ASC`로 정렬한다.
- ZIP entry timestamp는 `1980-01-01T00:00:00`, 권한은 regular file `0644`, 압축은 DEFLATE level 9로 고정한다. entry는 이름순이며 manifest JSON은 UTF-8, key 정렬, compact separator, LF로 직렬화한다.
- package record는 archive byte size와 SHA-256을 manifest 바깥에 함께 보존한다.
- download 전에 package checksum을 검증하고 불일치하면 참조를 제공하지 않는다.

## 안전한 실패 표현

외부/운영자 응답은 `artifact_missing`, `artifact_stale`, `invalid_artifact`, `package_size_exceeded`, `integrity_check_failed`, `assembly_storage_error` 같은 allowlist code만 반환한다. 실제 path와 내부 exception은 보안 로그에도 원문 payload와 함께 남기지 않는다.

## 구현 결정

- 크기와 개수 상한은 [Checklist Model](delivery-checklist-model.md)의 정책을 사용하며 압축 전과 압축 후를 모두 검사한다.
- `package_checksum`은 self-reference를 피하기 위해 manifest JSON에는 넣지 않는다. immutable package record와 manifest/download metadata 응답에서만 제공한다.
- `delivery-note.txt`는 64 KiB 이하 UTF-8 plain text다. NUL과 CR을 포함한 제어문자를 거부하며 LF와 TAB만 허용한다. Phase 3 기본 template에는 생성 source가 없으므로 보통 생략된다.
- download reference는 256-bit random opaque token이고 DB에는 SHA-256 digest만 저장한다. 발급 후 15분 동안 한 번만 사용할 수 있으며 사용 시 project ownership, capability, package 상태와 checksum을 다시 검증한다.

## 관련 문서

- [Checklist Model](delivery-checklist-model.md)
- [Readiness Contract](delivery-readiness-contract.md)
- [Package Assembly](delivery-package-assembly.md)
- [Security and Operator UX](delivery-package-operator-ux.md)
