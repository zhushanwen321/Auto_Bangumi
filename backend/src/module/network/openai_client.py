import json
import logging
from typing import Any, TypeVar

from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def create_openai_client(config: dict) -> OpenAI | AzureOpenAI:
    """从 config dict 创建 OpenAI 或 AzureOpenAI client。"""
    api_type = config.get("api_type", "openai")
    if api_type == "azure":
        return AzureOpenAI(
            api_key=config.get("api_key", ""),
            base_url=config.get("api_base", "https://api.openai.com/v1"),
            azure_deployment=config.get("deployment_id", ""),
            api_version=config.get("api_version", "2023-05-15"),
        )
    return OpenAI(
        api_key=config.get("api_key", ""),
        base_url=config.get("api_base", "https://api.openai.com/v1"),
    )


def _do_chat(
    client: OpenAI | AzureOpenAI,
    model: str,
    messages: list[dict[str, str]],
    **kwargs: Any,
):
    """发送 chat completion 请求，自动处理 response_format 兼容性。"""
    try:
        return client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            **kwargs,
        )
    except Exception:
        logger.debug("[LLM] response_format=json_object not supported, falling back")
        return client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )


def call_json(
    client: OpenAI | AzureOpenAI,
    model: str,
    messages: list[dict[str, str]],
    response_model: type[T] | None = None,
    **kwargs: Any,
) -> dict | T:
    """调用 LLM 并期望 JSON 响应。

    可选传入 response_model (Pydantic model) 进行 schema 校验：
    - 校验通过：返回 model 实例
    - 校验失败：返回带默认值的空实例
    - 不传 response_model：返回原始 dict
    """
    response = _do_chat(client, model, messages, **kwargs)
    content = response.choices[0].message.content or "{}"

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 提取 JSON 部分以提高兼容性
        try:
            json_str = content[content.index("{") : content.rindex("}") + 1]
            data = json.loads(json_str)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[LLM] Invalid JSON response: %s", e)
            if response_model:
                return response_model.model_construct()
            return {}

    if response_model:
        try:
            return response_model.model_validate(data)
        except Exception as e:
            logger.warning("[LLM] Schema validation failed: %s", e)
            return response_model.model_construct()

    return data


def call_text(
    client: OpenAI | AzureOpenAI,
    model: str,
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> str:
    """简单文本补全，不做 format 约束。用于测试连接等场景。"""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    return response.choices[0].message.content or ""
