"""ENABLE_WEB_SEARCH=0 또는 ENABLE_OUTBOUND_HTTP=0일 때 사용하는 검색 어댑터. 호출 시 PermissionError."""
import logging
from typing import List

from mellow_link.adapters.search.base import SearchAdapter, SearchResult
from mellow_link.core.null_providers import log_airgap_block

logger = logging.getLogger(__name__)


class NullSearchAdapter(SearchAdapter):
    """웹 검색 비활성화 시 사용. search() 호출 시 PermissionError."""

    def __init__(self, *, blocked_flag: str = "ENABLE_WEB_SEARCH", detail: str = "웹 검색 비활성화") -> None:
        self._blocked_flag = blocked_flag
        self._detail = detail

    async def search(
        self,
        query: str,
        top_k: int = 5,
        scrape_content: bool = True,
    ) -> List[SearchResult]:
        log_airgap_block("NullSearchAdapter.search", self._blocked_flag, self._detail)
        raise PermissionError(
            f"{self._blocked_flag}=0. {self._detail}(폐쇄망/정책)."
        )
