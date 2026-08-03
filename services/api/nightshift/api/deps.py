"""Request-scoped dependencies.

`current_user_id` is the single place the codebase learns who is acting.
AMENDMENTS A3 defers auth to M5, and this is what makes that a one-file change
rather than a sweep: today it returns the seeded dev user, and every route
already filters on whatever it returns.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends

from nightshift.config import Settings, get_settings


async def current_user_id(settings: Annotated[Settings, Depends(get_settings)]) -> UUID:
    return settings.dev_user_id


CurrentUserId = Annotated[UUID, Depends(current_user_id)]
