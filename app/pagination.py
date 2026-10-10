"""Shared HTTP pagination limits prevent unbounded SQLite offsets."""

from typing import Annotated

from fastapi import Query

MAX_PAGE = 1_000_000
PageNumber = Annotated[int, Query(ge=1, le=MAX_PAGE)]
