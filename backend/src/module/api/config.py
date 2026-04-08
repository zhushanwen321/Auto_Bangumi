import asyncio
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing_extensions import Literal

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
    """后台批量补全 dandanplay_title，支持简单搜索和 AI 增强搜索。"""
    try:
        from module.database import Database

        # 先在独立 session 中查询需要的记录（只取 id 和 official_title）
        with Database() as db:
            records = db.bangumi.get_bangumi_missing_dandanplay()
        if not records:
            logger.info("[Dandanplay] No missing titles to update")
            return
        # 提取简单数据，避免 ORM 对象 detach 问题
        record_data = [
            {"id": r.id, "official_title": r.official_title} for r in records
        ]
        logger.info("[Dandanplay] Batch update triggered: %d records", len(record_data))

        # 根据 AI 开关选择搜索方式
        if (
            settings.experimental_openai.enable
            and settings.experimental_openai.features.enable_dandanplay_match
        ):
            from module.searcher.dandanplay import batch_update_dandanplay_titles_ai

            await batch_update_dandanplay_titles_ai(
                records=record_data,
                app_id=settings.dandanplay.app_id,
                app_secret=settings.dandanplay.app_secret,
                openai_config=settings.experimental_openai.dict(
                    exclude={"enable", "features"}
                ),
            )
        else:
            from module.searcher.dandanplay import batch_update_dandanplay_titles

            await batch_update_dandanplay_titles(
                records=record_data,
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
            old_method not in ("dandanplay", "subtitle_dandanplay")
            and new_method in ("dandanplay", "subtitle_dandanplay")
        ):
            _dandanplay_task = asyncio.create_task(_trigger_dandanplay_batch())
            # 保存引用避免 GC 回收导致任务静默丢失

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


class TestOpenAIRequest(BaseModel):
    api_key: str = Field(..., description="OpenAI API key")
    api_base: str = Field("https://api.openai.com/v1", description="API base URL")
    api_type: Literal["azure", "openai"] = Field("openai", description="API type")
    api_version: str = Field("2023-05-15", description="API version (Azure)")
    model: str = Field("gpt-3.5-turbo", description="Model name")
    deployment_id: str = Field("", description="Azure deployment ID")


class TestOpenAIResponse(BaseModel):
    success: bool
    message_en: str
    message_zh: str


def _do_test_completion(req: TestOpenAIRequest) -> tuple[bool, str]:
    """同步执行一次最小 chat completion 来验证连接。"""
    from module.network.openai_client import create_openai_client

    client = create_openai_client(req.model_dump())
    model = req.deployment_id if req.api_type == "azure" and req.deployment_id else req.model
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=1,
    )
    return True, response.model or model


@router.post(
    "/test-openai",
    response_model=TestOpenAIResponse,
    dependencies=[Depends(get_current_user)],
)
async def test_openai(req: TestOpenAIRequest):
    """Test LLM connection with the provided configuration (no side effects)."""
    try:
        success, info = await asyncio.to_thread(_do_test_completion, req)
        return TestOpenAIResponse(
            success=True,
            message_en=f"Connection successful, model: {info}",
            message_zh=f"连接成功，模型: {info}",
        )
    except Exception as e:
        err = str(e)
        # 截断过长的错误信息（如 HTML 响应），只保留前 200 字符
        if len(err) > 200:
            err = err[:200] + "..."
        return TestOpenAIResponse(
            success=False,
            message_en=f"Connection failed: {err}",
            message_zh=f"连接失败: {err}",
        )
