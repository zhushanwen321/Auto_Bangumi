import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from module.conf import settings
from module.models import APIResponse, Config
from module.security.api import UNAUTHORIZED, get_current_user

router = APIRouter(prefix="/config", tags=["config"])
logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = ("password", "api_key", "token", "secret")
_MASK = "********"


def _is_sensitive(key: str) -> bool:
    return any(s in key.lower() for s in _SENSITIVE_KEYS)


def _sanitize_dict(d: dict) -> dict:
    """Recursively mask string values whose keys contain sensitive keywords."""
    result = {}
    for k, v in d.items():
        if isinstance(v, dict):
            result[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            result[k] = [
                _sanitize_dict(item) if isinstance(item, dict) else item for item in v
            ]
        elif isinstance(v, str) and _is_sensitive(k):
            result[k] = _MASK
        else:
            result[k] = v
    return result


def _restore_masked(incoming: dict, current: dict) -> dict:
    """Replace masked sentinel values with real values from current config."""
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(current.get(k), dict):
            _restore_masked(v, current[k])
        elif isinstance(v, list) and isinstance(current.get(k), list):
            cur_list = current[k]
            for i, item in enumerate(v):
                if (
                    isinstance(item, dict)
                    and i < len(cur_list)
                    and isinstance(cur_list[i], dict)
                ):
                    _restore_masked(item, cur_list[i])
        elif v == _MASK and _is_sensitive(k):
            incoming[k] = current.get(k, v)
    return incoming


@router.get("/get", dependencies=[Depends(get_current_user)])
async def get_config():
    """Return the current configuration with sensitive fields masked."""
    return _sanitize_dict(settings.dict())


async def _trigger_dandanplay_batch():
    """后台批量补全 dandanplay_title。"""
    try:
        from module.database import Database
        from module.searcher.dandanplay import batch_update_dandanplay_titles

        with Database() as db:
            records = db.bangumi.get_bangumi_missing_dandanplay()
        if not records:
            logger.info("[Dandanplay] No missing titles to update")
            return
        logger.info("[Dandanplay] Batch update triggered: %d records", len(records))
        await batch_update_dandanplay_titles(
            records=records,
            db=db,
            app_id=settings.dandanplay.app_id,
            app_secret=settings.dandanplay.app_secret,
        )
    except Exception as e:
        logger.warning("[Dandanplay] Batch update failed: %s", e)


@router.patch(
    "/update", response_model=APIResponse, dependencies=[Depends(get_current_user)]
)
async def update_config(config: Config):
    """Persist and reload configuration from the supplied payload."""
    try:
        old_method = settings.bangumi_manage.rename_method
        config_dict = _restore_masked(config.dict(), settings.dict())
        settings.save(config_dict=config_dict)
        settings.load()
        # update_rss()
        logger.info("Config updated")

        # 检测 rename_method 是否切换到 dandanplay，触发全量补全
        new_method = settings.bangumi_manage.rename_method
        if (
            old_method != "dandanplay"
            and new_method == "dandanplay"
            and settings.dandanplay.enable
        ):
            asyncio.create_task(_trigger_dandanplay_batch())

        return JSONResponse(
            status_code=200,
            content={
                "msg_en": "Update config successfully.",
                "msg_zh": "更新配置成功。",
            },
        )
    except Exception as e:
        logger.warning(e)
        return JSONResponse(
            status_code=406,
            content={"msg_en": "Update config failed.", "msg_zh": "更新配置失败。"},
        )
