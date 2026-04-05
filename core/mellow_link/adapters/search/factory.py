"""
검색 어댑터 Factory.

ENABLE_WEB_SEARCH=0 또는 ENABLE_OUTBOUND_HTTP=0 → NullSearchAdapter.
둘 다 1이면 DuckDuckGoSearchAdapter.
"""
import logging
from typing import Optional

from mellow_link.adapters.search.base import SearchAdapter, SearchResult
from mellow_link.adapters.search.search_null import NullSearchAdapter
from mellow_link.adapters.search.search_duckduckgo import DuckDuckGoSearchAdapter

logger = logging.getLogger(__name__)

_search_instance: Optional[SearchAdapter] = None
_search_cache_key: Optional[tuple[bool, bool]] = None


def get_search() -> SearchAdapter:
    global _search_instance, _search_cache_key
    try:
        from mellow_link.config.settings import get_settings
        s = get_settings()
        cache_key = (bool(s.allow_outbound_http()), bool(s.allow_web_search()))
        if _search_instance is not None and _search_cache_key == cache_key:
            return _search_instance
        if not s.allow_outbound_http():
            _search_instance = NullSearchAdapter(
                blocked_flag="ENABLE_OUTBOUND_HTTP",
                detail="외부 HTTP가 비활성화되었습니다",
            )
            logger.info("[SearchFactory] Using NullSearchAdapter (ENABLE_OUTBOUND_HTTP=0)")
        elif not s.allow_web_search():
            _search_instance = NullSearchAdapter(
                blocked_flag="ENABLE_WEB_SEARCH",
                detail="웹 검색이 비활성화되었습니다",
            )
            logger.info("[SearchFactory] Using NullSearchAdapter (ENABLE_WEB_SEARCH=0)")
        else:
            _search_instance = DuckDuckGoSearchAdapter()
            logger.info("[SearchFactory] Using DuckDuckGoSearchAdapter")
        _search_cache_key = cache_key
    except Exception as e:
        logger.warning("[SearchFactory] allow check failed, defaulting to Null: %s", e)
        _search_instance = NullSearchAdapter()
        _search_cache_key = None
    return _search_instance
