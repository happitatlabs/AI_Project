from __future__ import annotations

import re
from collections import OrderedDict
from typing import Iterable

from .schemas import AnonymizationAsset, IdentifierToken


class DocumentEntityTokenizer:
    """Extract document-style sensitive entities from SML presentation content only."""

    _SML_HEADER = "[SML v1]"
    _SUPPORTED_HINTS = ("presentation", "slide", "deck")
    _SUPPORTED_EXTENSIONS = (".ppt", ".pptx")
    _GENERIC_SECTION_LINES = {
        "[sml v1]",
        "texts:",
        "tables:",
        "charts:",
        "notes:",
        "visual_elements:",
    }
    _PRIORITY = {
        "client_name": 0,
        "project_name": 1,
        "business_name": 2,
        "contract_name": 3,
        "company_name": 4,
        "organization_name": 5,
        "department_name": 6,
        "person_name": 7,
        "email": 8,
        "phone": 9,
        "address": 10,
    }
    _LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "client_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:고객사명|고객사|발주처|client(?:\s+name)?|customer(?:\s+name)?)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "company_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:회사명|수행사|공급사|vendor|contractor|partner(?:\s+company)?)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "organization_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:기관명|기관|조직명|organization(?:\s+name)?|agency)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "department_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:부서명|부서|담당부서|주관부서|department|division|team|office)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "person_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:담당자|작성자|발표자|책임자|owner|presenter|speaker|contact(?:\s+person)?|manager|pm)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "project_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:프로젝트명|project(?:\s+name)?|과업명)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "business_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:사업명|과제명|initiative|program(?:\s+name)?)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "contract_name",
            re.compile(
                r"^(?:[-*]\s*)?(?:계약명|용역명|contract(?:\s+name)?)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
        (
            "address",
            re.compile(
                r"^(?:[-*]\s*)?(?:주소|소재지|address|location)\s*[:：]?\s*(?P<value>.+?)\s*$",
                re.IGNORECASE,
            ),
        ),
    )
    _TITLE_PATTERN = re.compile(r"^title\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)
    _EMAIL_PATTERN = re.compile(r"\b(?P<value>[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
    _PHONE_PATTERN = re.compile(
        r"(?P<value>(?<!\d)(?:\+?82[-\s]?)?(?:0\d{1,2}|1\d{3})[-\s]?\d{3,4}[-\s]?\d{4}(?!\d))"
    )
    _ADDRESS_INLINE_PATTERN = re.compile(
        r"(?P<value>(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
        r"[^\n]{4,}?(?:로|길|동|읍|면|리)\s*\d[^\n]*)"
    )
    _KOREAN_COMPANY_PATTERN = re.compile(
        r"(?P<value>(?:주식회사\s*)?[가-힣A-Za-z0-9&().\-/ ]{2,}"
        r"(?:㈜|\(주\)|주식회사|공사|공단|협회|재단|은행|카드|증권|보험|병원|대학교|대학|센터|연구원|청|그룹|테크|기업|산업|전자|건설|항공|통신|시스템즈|시스템|컨설팅))"
    )
    _ENGLISH_ORG_PATTERN = re.compile(
        r"(?P<value>[A-Z][A-Za-z0-9&().\-/]*(?:\s+[A-Z][A-Za-z0-9&().\-/]*)*"
        r"\s+(?:Inc\.|Corp\.|Corporation|Ltd\.|Limited|Company|Co\.|University|Bank|Hospital|Foundation|Institute))"
    )
    _DEPARTMENT_PATTERN = re.compile(
        r"(?P<value>[가-힣A-Za-z0-9&().\-/ ]{2,}(?:팀|본부|실|센터|부|처|국|원|랩|Lab|Team|Division|Office))$"
    )
    _PERSON_KO_PATTERN = re.compile(r"(?P<value>[가-힣]{2,4})(?:\s*(?:PM|PL|TL|님|매니저|책임|수석|선임|부장|차장|과장|대리))?$")
    _PERSON_EN_PATTERN = re.compile(
        r"(?P<value>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})(?:\s+(?:PM|PL|TL|Manager|Lead|Director))?$"
    )
    _PERSON_EN_SCAN_PATTERN = re.compile(
        r"\b(?P<value>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}(?:\s+(?:PM|PL|TL|Manager|Lead|Director))?)\b"
    )
    _PERSON_ROLE_PREFIX_PATTERN = re.compile(
        r"(?:^|[\s\-*/|,;])"
        r"(?:담당자|작성자|발표자|책임자|담당|작성|책임|문의|연락처|contact(?:\s+person)?|owner|speaker|presenter|manager|pm)"
        r"(?:\s*[:：]\s*|\s+)(?P<value>[가-힣]{2,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        re.IGNORECASE,
    )
    _PERSON_ROLE_SUFFIX_PATTERN = re.compile(
        r"(?P<value>[가-힣]{2,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
        r"\s*(?:PM|PL|TL|님|매니저|책임|수석|선임|부장|차장|과장|대리|실장|팀장|본부장|리더|Manager|Lead|Director)\b",
        re.IGNORECASE,
    )
    _PERSON_CONTACT_NEARBY_PATTERN = re.compile(
        r"(?:^|[\s\-*/|,;])"
        r"(?:문의|연락처|contact(?:\s+person)?|담당자|담당)?"
        r"\s*[:：]?\s*(?P<value>[가-힣]{2,4}|[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
        r"\s*(?:[/|,;\-]|\s){1,3}"
        r"(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?:\+?82[-\s]?)?(?:0\d{1,2}|1\d{3})[-\s]?\d{3,4}[-\s]?\d{4})",
        re.IGNORECASE,
    )
    _PROJECT_KEYWORDS = ("프로젝트", "구축", "고도화", "개편", "혁신", "전환", "도입", "modernization", "project")
    _BUSINESS_KEYWORDS = ("사업", "과제", "initiative", "program", "isp", "bpr", "pi", "전략")
    _CONTRACT_KEYWORDS = ("계약", "용역", "contract", "engagement")
    _PERSON_SPLIT_PATTERN = re.compile(r"[/,|(]| 이메일| email| 전화| phone", re.IGNORECASE)
    _PERSON_LABELLESS_TOKEN_SPLIT_PATTERN = re.compile(r"[\s,;:/|(){}\[\]<>]+")
    _INLINE_CONTACT_LABEL_PATTERN = re.compile(r"^(?:[-*]\s*)?(?:이메일|email|전화|phone)\s*[:：]", re.IGNORECASE)
    _STRUCTURED_REQUIREMENT_ID_PATTERN = re.compile(
        r"\b(?:REQ|FR|NFR|IF|DB|SEC|TEST|PM|SFR|TER|SER|PMR|PSR)(?:-[A-Z])?-\d{2,3}\b",
        re.IGNORECASE,
    )
    _ACCOUNTING_DOMAIN_TERMS = {
        "배부",
        "배부기준",
        "원가배부",
        "공통비",
        "제조경비",
        "재료비",
        "노무비",
        "직접비",
        "간접비",
        "고정비",
        "변동비",
        "손익",
        "손익분석",
        "원가계산",
        "원가분석",
        "기준정보",
    }
    _BPR_GENERIC_TERMS = {
        "이행계획",
        "요건",
        "요구사항",
        "기능요구",
        "비기능요구",
        "인터페이스",
        "데이터",
        "보안",
        "품질",
        "테스트",
        "프로젝트관리",
        "변화관리",
        "교육",
        "운영",
        "관리체계",
        "추진조직",
        "로드맵",
        "일정",
        "비용",
        "기대효과",
        "정량효과",
        "정성효과",
        "과제",
        "세부과제",
    }
    _NON_NAME_GRAMMAR_TERMS = {
        "하여",
        "하고",
        "하는",
        "하지",
        "하에",
        "의해",
        "위해",
        "통한",
        "대한",
        "설정",
        "조회",
        "여부",
        "기능",
        "조직",
        "임명",
        "변경신청",
        "손해배상",
    }
    _PERSON_CANDIDATE_WHITELIST = {
        "원가",
        "원유",
        "분석",
        "시스템",
        "전산",
        "업무",
        "정보",
        "처리",
        "계층",
        "흐름",
        "데이터",
        "데이타",
        "입출력",
        "명세서",
        "구축",
        "최적화",
        "추진",
        "방안",
        "비전",
    }
    _PERSON_CANDIDATE_WHITELIST |= _ACCOUNTING_DOMAIN_TERMS
    _PERSON_CANDIDATE_WHITELIST |= _BPR_GENERIC_TERMS
    _PERSON_CANDIDATE_WHITELIST |= _NON_NAME_GRAMMAR_TERMS
    _GENERIC_DOCUMENT_TERMS = _PERSON_CANDIDATE_WHITELIST | {"개요", "범위", "구조", "검토"}
    _NON_REPLACEABLE_LABELLESS_PHRASES = {
        "배경",
        "필요성",
        "배경과 필요성",
        "기능 진단",
        "기능 진단 및 평가",
        "비전",
        "기초설계서",
        "흐름도",
        "화면",
        "운영방안",
        "개선안",
        "요구자료",
        "원가",
        "원가 계산",
        "원가 분석",
        "원가 시스템",
        "최적화 시스템",
        "구현",
        "설계",
        "전개",
        "개요",
    }
    _LOW_CONF_PLANNING_STEMS = {
        "방향",
        "계획",
        "이행",
        "목표",
        "모델",
        "전략",
        "체계",
        "개선",
        "구축",
        "설계",
        "운영",
        "관리",
        "지원",
        "효율",
        "표준",
        "최적",
        "분석",
        "도출",
        "요구",
        "도입",
        "고려",
        "정비",
        "대응",
        "방법",
        "아키텍처",
        "마스터",
        "비전",
        "개요",
        "소개",
        "목차",
        "흐름",
        "구성",
        "전제",
        "제약",
        "차세대",
        "노후",
        "최신",
        "신기술",
        "정보기술",
        "지능",
        "구체",
        "현실",
        "이상",
        "주요",
        "문제",
        "공정",
        "자료",
        "자재",
        "재료",
        "배부",
        "코드",
        "목록",
        "비율",
        "조회",
        "기록",
        "조성",
        "조달",
        "진행",
        "반복",
        "위치",
        "변동",
        "소요",
        "이익",
        "제품",
        "사업",
        "시스템",
        "방법론",
        "공정서",
        "차선책",
        "전면개편",
        "현장",
        "담당",
    }
    _LOW_CONF_NON_NAME_ENDINGS = (
        "적인",
        "화된",
        "하게",
        "하며",
        "하여",
        "한다",
        "된다",
        "도록",
        "하기",
        "해서",
        "으로써",
    )
    _DEPARTMENT_SUFFIXES = (
        "본부",
        "센터",
        "부서",
        "팀",
        "실",
        "처",
        "국",
        "랩",
        "Lab",
        "Team",
        "Division",
        "Office",
        "부",
    )
    _HEADING_OR_TOC_PATTERN = re.compile(
        r"^(?:목차|contents?|\d+(?:\.\d+)+[\.\)]?|\d+[\.\)]|[IVXLCM]+[\.\)]|[가-힣A-Za-z][\.\)])\s+",
        re.IGNORECASE,
    )
    _TOC_DOT_LEADER_PATTERN = re.compile(r"\.{2,}\s*\d+$")
    _PERSON_TECHNICAL_SUFFIXES = ("화", "계", "도")
    _COMMON_KOREAN_SURNAMES = {
        "김",
        "이",
        "박",
        "최",
        "정",
        "강",
        "조",
        "윤",
        "장",
        "임",
        "한",
        "오",
        "서",
        "신",
        "권",
        "황",
        "안",
        "송",
        "전",
        "홍",
        "유",
        "고",
        "문",
        "양",
        "손",
        "배",
        "백",
        "허",
        "남",
        "심",
        "노",
        "하",
        "곽",
        "성",
        "차",
        "주",
        "우",
        "구",
        "민",
        "진",
        "지",
        "엄",
        "원",
        "천",
        "방",
        "공",
        "현",
        "함",
        "변",
        "염",
        "여",
        "추",
        "도",
        "소",
        "석",
        "선",
        "설",
        "마",
        "길",
        "연",
        "위",
        "표",
        "명",
        "기",
        "반",
        "왕",
        "금",
        "옥",
        "육",
        "인",
        "맹",
        "제",
        "모",
        "장",
    }
    _COMPOUND_KOREAN_SURNAMES = {
        "남궁",
        "황보",
        "제갈",
        "선우",
        "사공",
        "독고",
        "서문",
        "동방",
        "어금",
    }
    _KOREAN_POSTPOSITIONS = (
        "으로",
        "에서",
        "에게",
        "까지",
        "부터",
        "처럼",
        "하고",
        "이며",
        "라고",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "와",
        "과",
        "도",
        "만",
        "로",
        "에",
        "께",
    )

    def tokenize(self, asset: AnonymizationAsset) -> list[IdentifierToken]:
        if not self.supports_asset(asset):
            return []

        text = asset.content_text or ""
        candidates: "OrderedDict[str, tuple[str, str]]" = OrderedDict()
        for line in self._candidate_lines(text):
            for kind, value in self._extract_labelled_entities(line):
                self._store_candidate(candidates, kind, value)
            for kind, value in self._extract_inline_entities(line):
                self._store_candidate(candidates, kind, value)

        existing_kinds = {kind for kind, _ in candidates.values()}
        for title in self._extract_title_values(text):
            for kind, value in self._classify_title(title, existing_kinds=existing_kinds):
                self._store_candidate(candidates, kind, value)
                existing_kinds.add(kind)

        return [IdentifierToken(kind=kind, value=value) for kind, value in candidates.values()]

    def supports_asset(self, asset: AnonymizationAsset) -> bool:
        return self._supports_asset(asset)

    def _supports_asset(self, asset: AnonymizationAsset) -> bool:
        hint = (asset.kind_hint or "").lower()
        name = (asset.name or "").lower()
        text = asset.content_text or ""
        return (
            text.lstrip().startswith(self._SML_HEADER)
            or any(token in hint for token in self._SUPPORTED_HINTS)
            or name.endswith(self._SUPPORTED_EXTENSIONS)
        )

    def _candidate_lines(self, text: str) -> Iterable[str]:
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered in self._GENERIC_SECTION_LINES:
                continue
            if lowered.startswith(("presentation_file:", "slide_count:", "layout:", "[slide ")):
                continue
            yield line

    def _extract_labelled_entities(self, line: str) -> Iterable[tuple[str, str]]:
        for kind, pattern in self._LABEL_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            value = self._normalize_value(match.group("value"))
            if kind == "person_name":
                value = self._normalize_person_value(value)
            if self._is_valid_candidate(kind, value):
                yield kind, value
            break

    def has_supported_entity_label(self, line: str) -> bool:
        stripped = self._normalize_value(line)
        return self._INLINE_CONTACT_LABEL_PATTERN.match(stripped) is not None or any(
            pattern.match(stripped) for _, pattern in self._LABEL_PATTERNS
        )

    def _extract_inline_entities(self, line: str) -> Iterable[tuple[str, str]]:
        for match in self._EMAIL_PATTERN.finditer(line):
            value = self._normalize_value(match.group("value"))
            if self._is_valid_candidate("email", value):
                yield "email", value
        for match in self._PHONE_PATTERN.finditer(line):
            value = self._normalize_phone(match.group("value"))
            if self._is_valid_candidate("phone", value):
                yield "phone", value
        for match in self._ADDRESS_INLINE_PATTERN.finditer(line):
            value = self._normalize_value(match.group("value"))
            if self._is_valid_candidate("address", value):
                yield "address", value

        stripped = self._normalize_bullet_content(line)
        if stripped and self._looks_like_department(stripped):
            yield "department_name", stripped

    def _extract_title_values(self, text: str) -> Iterable[str]:
        for raw_line in (text or "").splitlines():
            match = self._TITLE_PATTERN.match(raw_line.strip())
            if not match:
                continue
            value = self._normalize_value(match.group("value"))
            if value:
                yield value

    def _classify_title(self, title: str, *, existing_kinds: set[str]) -> Iterable[tuple[str, str]]:
        lowered = title.lower()
        if "contract_name" not in existing_kinds and any(keyword in lowered for keyword in self._CONTRACT_KEYWORDS):
            yield "contract_name", title
        elif "business_name" not in existing_kinds and any(keyword in lowered for keyword in self._BUSINESS_KEYWORDS):
            yield "business_name", title
        elif "project_name" not in existing_kinds and any(keyword in lowered for keyword in self._PROJECT_KEYWORDS):
            yield "project_name", title
        elif "organization_name" not in existing_kinds and self._looks_like_company_or_org(title):
            yield "organization_name", title

    def _store_candidate(self, candidates: "OrderedDict[str, tuple[str, str]]", kind: str, value: str) -> None:
        normalized = self._normalize_value(value)
        if not self._is_valid_candidate(kind, normalized):
            return
        existing = candidates.get(normalized)
        if existing is None:
            candidates[normalized] = (kind, normalized)
            return
        existing_kind = existing[0]
        if self._PRIORITY.get(kind, 999) < self._PRIORITY.get(existing_kind, 999):
            candidates[normalized] = (kind, normalized)

    def _normalize_person_value(self, value: str) -> str:
        head = self._PERSON_SPLIT_PATTERN.split(value, maxsplit=1)[0]
        normalized = self._normalize_value(head)
        for pattern in (self._PERSON_KO_PATTERN, self._PERSON_EN_PATTERN):
            match = pattern.match(normalized)
            if match:
                return self._normalize_value(match.group("value"))
        return normalized

    @staticmethod
    def _normalize_phone(value: str) -> str:
        digits = re.sub(r"[^\d+]", "", value or "")
        if digits.startswith("+82") and len(digits) >= 12:
            return f"+82-{digits[3:5]}-{digits[5:9]}-{digits[9:]}"
        return re.sub(r"\s+", "", value or "").strip()

    @staticmethod
    def _normalize_bullet_content(line: str) -> str:
        return re.sub(r"^[-*]\s*", "", (line or "").strip())

    @staticmethod
    def _normalize_value(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip(" -:;,.")).strip()

    def _looks_like_department(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        if len(normalized) > 60 or any(token in normalized for token in (":", "@", "/", "[", "]")):
            return False
        if self._contains_accounting_domain_term(normalized):
            return False
        return self._matches_department_suffix(normalized)

    def _looks_like_company_or_org(self, value: str) -> bool:
        if len(value) > 80 or any(token in value for token in ("@", "[", "]")):
            return False
        return bool(self._KOREAN_COMPANY_PATTERN.fullmatch(value) or self._ENGLISH_ORG_PATTERN.fullmatch(value))

    def _compact_value(self, value: str) -> str:
        return re.sub(r"\s+", "", self._normalize_value(value))

    def _contains_accounting_domain_term(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        compact = self._compact_value(normalized)
        compact_terms = {term.replace(" ", "") for term in self._ACCOUNTING_DOMAIN_TERMS}
        if normalized in self._ACCOUNTING_DOMAIN_TERMS or compact in compact_terms:
            return True
        if compact.endswith("배부"):
            return True
        for match in re.finditer(r"[가-힣A-Za-z0-9]+", normalized):
            token = self._trim_korean_postposition(match.group(0))
            if token in self._ACCOUNTING_DOMAIN_TERMS or token.replace(" ", "") in compact_terms:
                return True
        return False

    def _matches_department_suffix(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        lowered = normalized.lower()
        for suffix in self._DEPARTMENT_SUFFIXES:
            if suffix.isascii():
                if not lowered.endswith(suffix.lower()):
                    continue
                stem = normalized[: -len(suffix)].strip()
            else:
                if not normalized.endswith(suffix):
                    continue
                stem = normalized[: -len(suffix)].strip()
            if len(stem) < 2:
                return False
            if self._contains_accounting_domain_term(stem):
                return False
            if suffix == "부" and normalized.endswith("배부"):
                return False
            return True
        return False

    def _trim_korean_postposition(self, value: str) -> str:
        normalized = self._normalize_value(value)
        for suffix in sorted(self._KOREAN_POSTPOSITIONS, key=len, reverse=True):
            if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
                return normalized[: -len(suffix)]
        return normalized

    def _is_person_stop_term(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        if normalized in self._PERSON_CANDIDATE_WHITELIST:
            return True
        for suffix in self._PERSON_TECHNICAL_SUFFIXES:
            if normalized.endswith(suffix) and normalized[: -len(suffix)] in self._PERSON_CANDIDATE_WHITELIST:
                return True
        return False

    def is_generic_document_phrase(self, value: str, *, ignore_tokens: set[str] | None = None) -> bool:
        normalized_ignore = {self._normalize_value(token) for token in (ignore_tokens or set()) if token}
        terms = [
            self._trim_korean_postposition(match.group(0))
            for match in re.finditer(r"[가-힣A-Za-z0-9]+", self._normalize_value(value))
        ]
        informative_terms = [term for term in terms if len(term) >= 2 and term not in normalized_ignore]
        if not informative_terms:
            return False
        for term in informative_terms:
            if re.fullmatch(r"[A-Za-z0-9]+", term):
                return False
            if term in self._GENERIC_DOCUMENT_TERMS:
                continue
            if any(term.endswith(suffix) and term[: -len(suffix)] in self._PERSON_CANDIDATE_WHITELIST for suffix in self._PERSON_TECHNICAL_SUFFIXES):
                continue
            return False
        return True

    def _looks_like_korean_person_name(self, value: str, *, allow_two_char: bool = False) -> bool:
        if len(value) == 2:
            return allow_two_char and value[0] in self._COMMON_KOREAN_SURNAMES
        if len(value) == 3:
            return value[0] in self._COMMON_KOREAN_SURNAMES
        if len(value) == 4:
            return value[0] in self._COMMON_KOREAN_SURNAMES or value[:2] in self._COMPOUND_KOREAN_SURNAMES
        return False

    def _looks_like_heading_or_toc_line(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        return bool(self._HEADING_OR_TOC_PATTERN.match(normalized) or self._TOC_DOT_LEADER_PATTERN.search(normalized))

    def _looks_like_plain_heading_phrase(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        if not normalized or self._has_explicit_person_context(normalized):
            return False
        tokens = [match.group(0) for match in re.finditer(r"[가-힣A-Za-z0-9]+", normalized)]
        if not tokens or len(tokens) > 8:
            return False
        first_token = self._normalize_value(tokens[0])
        compact = "".join(tokens)
        if self._PERSON_KO_PATTERN.match(first_token) and self._looks_like_korean_person_name(first_token):
            return False
        if self._PERSON_EN_PATTERN.match(first_token) and " " in first_token:
            return False
        if len(compact) > 48:
            return False
        return any(stem in compact for stem in self._LOW_CONF_PLANNING_STEMS)

    def _looks_like_structured_requirement_line(self, value: str, *, section: str = "body") -> bool:
        normalized = self._normalize_value(value)
        if not normalized:
            return False
        if self._STRUCTURED_REQUIREMENT_ID_PATTERN.search(normalized):
            return True
        if section.lower() == "tables" and normalized.count("|") >= 2:
            return True
        return False

    def _has_explicit_person_context(self, value: str) -> bool:
        normalized = self._normalize_bullet_content(value)
        if not normalized:
            return False
        if self._PERSON_ROLE_PREFIX_PATTERN.search(normalized):
            return True
        if self._PERSON_ROLE_SUFFIX_PATTERN.search(normalized):
            return True
        if (self._EMAIL_PATTERN.search(normalized) or self._PHONE_PATTERN.search(normalized)) and self._PERSON_CONTACT_NEARBY_PATTERN.search(normalized):
            return True
        return False

    def _contains_low_conf_planning_hint(self, value: str) -> bool:
        normalized = self._normalize_value(value)
        compact = normalized.replace(" ", "")
        if not compact:
            return False
        if any(stem in compact for stem in self._LOW_CONF_PLANNING_STEMS):
            return True
        return any(compact.endswith(ending) for ending in self._LOW_CONF_NON_NAME_ENDINGS)

    def _line_contains_potential_person_token(self, value: str) -> bool:
        normalized = self._normalize_bullet_content(value)
        for raw_token in re.findall(r"[가-힣A-Za-z0-9]+", normalized):
            token = self._normalize_value(raw_token)
            if self._PERSON_KO_PATTERN.match(token) and self._looks_like_korean_person_name(token):
                return True
            if self._PERSON_EN_PATTERN.match(token) and " " in token:
                return True
        return False

    def _should_suppress_low_conf_term(self, token: str, *, line: str, section: str = "body") -> bool:
        normalized_line = self._normalize_bullet_content(line)
        normalized_token = self._normalize_value(token)
        if not normalized_token:
            return True
        if self._has_explicit_person_context(normalized_line):
            return False
        if self._looks_like_plain_heading_phrase(normalized_line):
            return True
        if self._contains_accounting_domain_term(normalized_token):
            return True
        if self._contains_low_conf_planning_hint(normalized_token):
            return True
        if section.lower() in {"texts", "notes"}:
            tokens = re.findall(r"[가-힣A-Za-z0-9]+", normalized_line)
            if len(tokens) >= 4 and self._contains_low_conf_planning_hint(normalized_line) and not self._line_contains_potential_person_token(normalized_line):
                return True
        return False

    def _has_specific_non_generic_term(self, value: str, *, ignore_tokens: set[str] | None = None) -> bool:
        normalized_ignore = {self._normalize_value(token) for token in (ignore_tokens or set()) if token}
        for match in re.finditer(r"[가-힣A-Za-z0-9]+", self._normalize_value(value)):
            term = self._trim_korean_postposition(match.group(0))
            if len(term) < 2 or term in normalized_ignore:
                continue
            if term in self._GENERIC_DOCUMENT_TERMS or term in self._NON_REPLACEABLE_LABELLESS_PHRASES:
                continue
            if any(term.endswith(suffix) and term[: -len(suffix)] in self._PERSON_CANDIDATE_WHITELIST for suffix in self._PERSON_TECHNICAL_SUFFIXES):
                continue
            return True
        return False

    def should_replace_label_less_candidate(self, kind: str, value: str, *, ignore_tokens: set[str] | None = None) -> bool:
        normalized = self._normalize_value(value)
        lowered = normalized.lower()
        if not normalized:
            return False
        if normalized in self._NON_REPLACEABLE_LABELLESS_PHRASES:
            return False
        if self.is_generic_document_phrase(normalized, ignore_tokens=ignore_tokens):
            return False
        if kind in {"organization_name", "company_name"}:
            return bool(self._KOREAN_COMPANY_PATTERN.fullmatch(normalized) or self._ENGLISH_ORG_PATTERN.fullmatch(normalized))
        if kind == "department_name":
            return self._looks_like_department(normalized)
        if kind == "project_name":
            return (
                any(keyword in lowered for keyword in ("프로젝트", "project", "시스템", "system", "고도화", "구축", "개발"))
                and self._has_specific_non_generic_term(normalized, ignore_tokens=ignore_tokens)
            )
        if kind == "business_name":
            return any(keyword in lowered for keyword in self._BUSINESS_KEYWORDS) and self._has_specific_non_generic_term(
                normalized,
                ignore_tokens=ignore_tokens,
            )
        if kind == "contract_name":
            return any(keyword in lowered for keyword in self._CONTRACT_KEYWORDS) and self._has_specific_non_generic_term(
                normalized,
                ignore_tokens=ignore_tokens,
            )
        return kind in {"person_name", "email", "phone", "address"}

    def is_valid_label_less_person_candidate(
        self,
        value: str,
        *,
        original_token: str | None = None,
        context: str = "standalone",
    ) -> bool:
        original = self._normalize_value(original_token or value)
        candidate = self._normalize_person_value(self._trim_korean_postposition(original))
        if not candidate:
            return False
        if self._is_person_stop_term(candidate):
            return False
        if self._PERSON_KO_PATTERN.match(candidate):
            if context not in {"role_hint", "contact"}:
                return False
            if not self._looks_like_korean_person_name(candidate, allow_two_char=True):
                return False
            return True
        if self._PERSON_EN_PATTERN.match(candidate):
            if context not in {"role_hint", "contact"}:
                return False
            has_role_hint = bool(re.search(r"\b(?:PM|PL|TL|Manager|Lead|Director)\b", original))
            return " " in candidate or has_role_hint
        return False

    def iter_label_less_person_candidates(self, line: str, *, section: str = "body") -> Iterable[str]:
        normalized_line = self._normalize_bullet_content(line)
        if not normalized_line:
            return []
        if section.lower() in {"title", "heading"}:
            return []
        if self._looks_like_heading_or_toc_line(normalized_line):
            return []
        if self._looks_like_structured_requirement_line(normalized_line, section=section) and not self._has_explicit_person_context(normalized_line):
            return []
        seen: "OrderedDict[str, None]" = OrderedDict()
        for pattern in (self._PERSON_ROLE_PREFIX_PATTERN, self._PERSON_ROLE_SUFFIX_PATTERN):
            for match in pattern.finditer(normalized_line):
                token = self._normalize_value(match.group("value"))
                candidate = self._normalize_person_value(self._trim_korean_postposition(token))
                if self.is_valid_label_less_person_candidate(candidate, original_token=token, context="role_hint"):
                    seen.setdefault(candidate, None)
        if self._EMAIL_PATTERN.search(normalized_line) or self._PHONE_PATTERN.search(normalized_line):
            for match in self._PERSON_CONTACT_NEARBY_PATTERN.finditer(normalized_line):
                token = self._normalize_value(match.group("value"))
                candidate = self._normalize_person_value(self._trim_korean_postposition(token))
                if self.is_valid_label_less_person_candidate(candidate, original_token=token, context="contact"):
                    seen.setdefault(candidate, None)
        return list(seen.keys())

    def iter_low_conf_term_candidates(
        self,
        line: str,
        *,
        section: str = "body",
        exclude: set[str] | None = None,
    ) -> Iterable[str]:
        normalized_line = self._normalize_bullet_content(line)
        if not normalized_line:
            return []
        if section.lower() in {"title", "heading"}:
            return []
        if self._looks_like_heading_or_toc_line(normalized_line):
            return []
        if self._looks_like_structured_requirement_line(normalized_line, section=section):
            return []
        if self._looks_like_plain_heading_phrase(normalized_line):
            return []
        excluded = {self._normalize_value(item) for item in (exclude or set()) if item}
        seen: "OrderedDict[str, None]" = OrderedDict()
        for raw_token in self._PERSON_LABELLESS_TOKEN_SPLIT_PATTERN.split(normalized_line):
            token = self._normalize_value(raw_token.strip("[]'\".!?"))
            if not token or token in excluded or self._is_person_stop_term(token) or self._looks_like_department(token):
                continue
            if self._should_suppress_low_conf_term(token, line=normalized_line, section=section):
                continue
            candidate = self._normalize_person_value(self._trim_korean_postposition(token))
            if candidate in excluded or self._is_person_stop_term(candidate) or self._looks_like_department(candidate):
                continue
            if self._should_suppress_low_conf_term(candidate, line=normalized_line, section=section):
                continue
            if self._PERSON_KO_PATTERN.match(candidate) and self._looks_like_korean_person_name(candidate):
                seen.setdefault(candidate, None)
                continue
            if self._PERSON_EN_PATTERN.match(candidate) and " " in candidate:
                seen.setdefault(candidate, None)
        return list(seen.keys())

    def _is_valid_candidate(self, kind: str, value: str) -> bool:
        if not value or value in {"-", "[NO_EXTRACTABLE_TEXT]"}:
            return False
        if len(value) < 2:
            return False
        lowered = value.lower()
        if lowered in self._GENERIC_SECTION_LINES:
            return False
        if kind in {"company_name", "organization_name", "department_name", "project_name", "client_name", "business_name", "contract_name"}:
            if len(value) > 120:
                return False
            if value.startswith("[") and value.endswith("]"):
                return False
        if kind == "person_name":
            return bool(self._PERSON_KO_PATTERN.match(value) or self._PERSON_EN_PATTERN.match(value))
        if kind == "email":
            return bool(self._EMAIL_PATTERN.fullmatch(value))
        if kind == "phone":
            return bool(self._PHONE_PATTERN.fullmatch(value))
        if kind == "address":
            return len(value) >= 8
        return True
