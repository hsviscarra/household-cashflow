"""The signed-in person and their own settings (ADR-026): the Both/Hernan/Lauren switch, table
columns and row size, saved views and Home widgets, kept as JSON per person so they follow them
from the laptop to the phone. Each person reads and writes only their own."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db.session import get_session
from app.models import UserSetting

router = APIRouter(prefix="/api/me/settings", tags=["me"])
DB = Annotated[Session, Depends(get_session)]
# Keys are short names the web app picks: "person", "table:transactions", "views", "home".
Key = Annotated[str, Path(pattern=r"^[a-z0-9][a-z0-9_.:/-]{0,99}$")]
MAX_VALUE = 20_000  # characters of JSON; columns and a few dozen saved views fit easily
MAX_KEYS = 100


class SettingsOut(BaseModel):
    """The signed-in person and their settings."""

    user: str
    settings: dict[str, Any]


class SettingIn(BaseModel):
    """A setting's value: any JSON."""

    value: Any


@router.get("", response_model=SettingsOut)
def get_settings(db: DB, request: Request) -> SettingsOut:
    """The signed-in person's saved settings (layouts, views, choices)."""
    user = current_user(request)
    rows = db.scalars(select(UserSetting).where(UserSetting.user_email == user))
    return SettingsOut(user=user, settings={r.key: json.loads(r.value_json) for r in rows})


@router.put("/{key}", response_model=SettingsOut)
def put_setting(db: DB, request: Request, key: Key, body: SettingIn) -> SettingsOut:
    """Keep one setting for the signed-in person; the value is any JSON up to a size limit."""
    user = current_user(request)
    text = json.dumps(body.value, separators=(",", ":"), ensure_ascii=False)
    if len(text) > MAX_VALUE:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "That setting is too large.")
    row = db.get(UserSetting, (user, key))
    if row is None:
        count = len(list(db.scalars(select(UserSetting.key).where(UserSetting.user_email == user))))
        if count >= MAX_KEYS:
            raise HTTPException(status.HTTP_409_CONFLICT, "Too many settings saved.")
        db.add(UserSetting(user_email=user, key=key, value_json=text))
    else:
        row.value_json = text
    db.commit()
    return get_settings(db, request)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting(db: DB, request: Request, key: Key) -> Response:
    """Forget one of the person's settings."""
    row = db.get(UserSetting, (current_user(request), key))
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
