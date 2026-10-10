"""Bounded database identities shared by HTTP inputs and content schemas."""

from typing import Annotated

from pydantic import Field

MAX_RECORD_ID = (1 << 63) - 1
RecordId = Annotated[int, Field(ge=1, le=MAX_RECORD_ID)]
