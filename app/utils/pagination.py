"""
Pagination helpers that work with MongoEngine QuerySets.
"""
from dataclasses import dataclass
from flask import request, current_app


@dataclass
class PageParams:
    page: int
    per_page: int


def get_page_params() -> PageParams:
    cfg = current_app.config
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", cfg["DEFAULT_PAGE_SIZE"]))
    except (TypeError, ValueError):
        per_page = cfg["DEFAULT_PAGE_SIZE"]
    per_page = min(max(1, per_page), cfg["MAX_PAGE_SIZE"])
    return PageParams(page=page, per_page=per_page)


def paginate_query(query, params: PageParams):
    """Paginate a MongoEngine QuerySet.

    Returns (items, total) where items is a list of documents for the
    requested page and total is the full match count.
    """
    total = query.count()
    items = list(
        query.skip((params.page - 1) * params.per_page).limit(params.per_page)
    )
    return items, total
