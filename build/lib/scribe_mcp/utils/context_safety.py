"""Context safety utilities for preventing token blowup in MCP tool responses.

Provides intelligent filtering, pagination, and token management for all Scribe MCP tools.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass

try:
    from .tokens import token_estimator
except ImportError:
    token_estimator = None


@dataclass
class PaginationInfo:
    """Pagination metadata for responses."""
    page: int
    page_size: int
    total_count: int
    has_next: bool
    has_prev: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total_count": self.total_count,
            "has_next": self.has_next,
            "has_prev": self.has_prev
        }


class SmartFilter:
    """Intelligent filtering for project lists and other large datasets."""

    # Patterns to identify test/temp projects that should be hidden by default
    TEST_PROJECT_PATTERNS = [
        r'^test-.*-[a-f0-9]{8,}$',  # test-xxxx-xxxxxxxx patterns
        r'^temp-.*-[a-f0-9]{8,}$',   # temp-xxxx-xxxxxxxx patterns
        r'^demo.*$',                 # demo projects
        r'^example.*$',              # example projects
        r'^mock.*$',                 # mock projects
        r'^sample.*$',               # sample projects
        r'^history-test-.*-[a-f0-9]{8,}$',  # history test projects
    ]

    @classmethod
    def is_test_project(cls, project_name: str) -> bool:
        """Check if a project name matches test/temp patterns."""
        project_lower = project_name.lower()
        return any(re.match(pattern, project_lower) for pattern in cls.TEST_PROJECT_PATTERNS)

    @classmethod
    def filter_projects(cls, projects: List[Dict[str, Any]],
                       include_test: bool = False,
                       sort_by: str = "last_accessed") -> List[Dict[str, Any]]:
        """Filter and sort projects intelligently."""
        filtered = []

        for project in projects:
            project_name = project.get("name", "")

            # Skip test projects unless explicitly requested
            if not include_test and cls.is_test_project(project_name):
                continue

            filtered.append(project)

        # Sort by specified criteria
        if sort_by == "name":
            filtered.sort(key=lambda p: p.get("name", "").lower())
        elif sort_by == "last_accessed":
            # Sort by last modified/accessed time if available
            filtered.sort(key=lambda p: p.get("last_modified", ""), reverse=True)
        else:
            # Default to name sorting
            filtered.sort(key=lambda p: p.get("name", "").lower())

        return filtered


class TokenGuard:
    """Manages token limits and provides warnings for context safety."""

    def __init__(self, warning_threshold: int = 4000, hard_limit: int = 8000):
        self.warning_threshold = warning_threshold
        self.hard_limit = hard_limit

    def estimate_tokens(self, data: Union[Dict, List, str]) -> int:
        """Estimate token count for response data."""
        if token_estimator is not None:
            return token_estimator.estimate_tokens(data)
        else:
            # Fallback to basic estimation
            import json
            if isinstance(data, str):
                return len(data) // 4
            elif isinstance(data, (dict, list)):
                return len(json.dumps(data)) // 4
            else:
                return len(str(data)) // 4

    def check_limits(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Check if response exceeds token limits and add warnings."""
        estimated_tokens = self.estimate_tokens(response)

        if estimated_tokens > self.hard_limit:
            return {
                "critical": True,
                "estimated_tokens": estimated_tokens,
                "hard_limit": self.hard_limit,
                "message": "Response exceeds hard token limit",
                "suggestion": "Use pagination or compact mode"
            }
        elif estimated_tokens > self.warning_threshold:
            return {
                "warning": True,
                "estimated_tokens": estimated_tokens,
                "warning_threshold": self.warning_threshold,
                "message": "Response approaching token limit",
                "suggestion": "Consider using pagination or compact mode"
            }

        return {"safe": True, "estimated_tokens": estimated_tokens}


class ResponsePaginator:
    """Handles intelligent pagination for large datasets."""

    DEFAULT_PAGE_SIZE = 5

    def __init__(self, default_page_size: int = DEFAULT_PAGE_SIZE):
        self.default_page_size = default_page_size

    def paginate(self, items: List[Dict[str, Any]],
                 page: int = 1,
                 page_size: Optional[int] = None) -> tuple[List[Dict[str, Any]], PaginationInfo]:
        """Paginate a list of items."""
        if page_size is None:
            page_size = self.default_page_size

        # Validate inputs (ensure integers)
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1

        try:
            page_size = int(page_size) if page_size is not None else None
        except (ValueError, TypeError):
            page_size = None

        if page_size is None:
            page_size = self.default_page_size

        if page < 1:
            page = 1
        if page_size < 1:
            page_size = self.default_page_size

        total_count = len(items)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        paginated_items = items[start_idx:end_idx]

        pagination_info = PaginationInfo(
            page=page,
            page_size=page_size,
            total_count=total_count,
            has_next=end_idx < total_count,
            has_prev=page > 1
        )

        return paginated_items, pagination_info

    def suggest_pagination(self, items: List[Dict[str, Any]],
                          token_guard: TokenGuard) -> Dict[str, Any]:
        """Suggest pagination based on token estimates."""
        # Estimate tokens for full response
        full_response = {"ok": True, "items": items, "count": len(items)}
        token_check = token_guard.check_limits(full_response)

        suggestions = []
        recommended_page_size = self.default_page_size

        if token_check.get("critical") or token_check.get("warning"):
            # Try different page sizes to find optimal
            for size in [3, 5, 10, 20]:
                test_items, _ = self.paginate(items, page=1, page_size=size)
                test_response = {"ok": True, "items": test_items, "count": size}
                test_check = token_guard.check_limits(test_response)

                if not test_check.get("warning") and not test_check.get("critical"):
                    recommended_page_size = size
                    break

            suggestions.append({
                "type": "pagination",
                "recommended_page_size": recommended_page_size,
                "total_pages": (len(items) + recommended_page_size - 1) // recommended_page_size,
                "reason": "Token optimization"
            })

        return {
            "suggestions": suggestions,
            "token_check": token_check,
            "estimated_full_tokens": token_check.get("estimated_tokens", 0)
        }


class ContextManager:
    """Main context safety coordinator."""

    def __init__(self, warning_threshold: int = 4000, hard_limit: int = 8000):
        self.smart_filter = SmartFilter()
        self.token_guard = TokenGuard(warning_threshold, hard_limit)
        self.paginator = ResponsePaginator()

    def prepare_response(self, items: List[Dict[str, Any]],
                        response_type: str = "list",
                        include_test: bool = False,
                        page: int = 1,
                        page_size: Optional[int] = None,
                        compact: bool = False) -> Dict[str, Any]:
        """
        Prepare a context-safe response with intelligent filtering and pagination.

        Args:
            items: List of items to include in response
            response_type: Type of response (affects filtering strategy)
            include_test: Whether to include test/temp projects
            page: Page number for pagination
            page_size: Number of items per page
            compact: Whether to use compact formatting

        Returns:
            Context-safe response with pagination info and token warnings
        """
        # Apply smart filtering
        filtered_items = self.smart_filter.filter_projects(
            items, include_test=include_test
        )

        # Apply pagination (ensure integer parameters)
        paginated_items, pagination_info = self.paginator.paginate(
            filtered_items, page=page, page_size=page_size
        )

        # Build base response
        response = {
            "ok": True,
            "items": paginated_items,
            "count": len(paginated_items),
            "pagination": pagination_info.to_dict(),
            "total_available": len(filtered_items),
            "filtered": len(items) != len(filtered_items)
        }

        # Add context safety info
        token_check = self.token_guard.check_limits(response)
        response["context_safety"] = {
            "estimated_tokens": token_check.get("estimated_tokens", 0),
            "filtering_applied": len(items) != len(filtered_items),
            "pagination_used": len(filtered_items) > len(paginated_items)
        }

        # Add warnings if needed
        if token_check.get("warning"):
            response["token_warning"] = {
                "estimated_tokens": token_check["estimated_tokens"],
                "warning_threshold": self.token_guard.warning_threshold,
                "message": token_check["message"],
                "suggestion": token_check["suggestion"]
            }
        elif token_check.get("critical"):
            response["token_critical"] = {
                "estimated_tokens": token_check["estimated_tokens"],
                "hard_limit": self.token_guard.hard_limit,
                "message": token_check["message"],
                "suggestion": token_check["suggestion"]
            }

        # Add compact mode info
        if compact:
            response["compact"] = True
            response["context_safety"]["compact_mode"] = True

        return response