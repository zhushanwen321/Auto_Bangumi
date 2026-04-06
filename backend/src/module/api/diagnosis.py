from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from module.diagnosis.models import FixAction
from module.diagnosis.service import DiagnosisService
from module.security.api import get_current_user

router = APIRouter(prefix="/rss", tags=["diagnosis"])
fix_router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


def _to_dict(obj: Any) -> Any:
    """递归将 dataclass 和 SQLModel 对象转为可 JSON 序列化的 dict。"""
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in fields(obj)}
    if hasattr(obj, "model_dump"):
        return {k: _to_dict(v) for k, v in obj.model_dump().items()}
    if isinstance(obj, list):
        return [_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


class ScanRequest(BaseModel):
    anime_titles: list[str] | None = None


class FixRequest(BaseModel):
    action: str
    torrent_name: str
    params: dict[str, Any] = {}


@router.get(
    "/{rss_id}/diagnosis/preview",
    dependencies=[Depends(get_current_user)],
)
async def preview(rss_id: int):
    with DiagnosisService() as svc:
        items = await svc.preview(rss_id)
    return {"data": [_to_dict(i) for i in items]}


@router.post(
    "/{rss_id}/diagnosis/scan",
    dependencies=[Depends(get_current_user)],
)
async def scan(rss_id: int, body: ScanRequest):
    with DiagnosisService() as svc:
        report = await svc.diagnose(rss_id, body.anime_titles)
    return {"data": _to_dict(report)}


@fix_router.post(
    "/fix",
    dependencies=[Depends(get_current_user)],
)
async def fix(body: FixRequest):
    with DiagnosisService() as svc:
        result = await svc.fix(
            FixAction(
                action=body.action,
                torrent_name=body.torrent_name,
                params=body.params,
            )
        )
    return {"data": {"success": result}}
