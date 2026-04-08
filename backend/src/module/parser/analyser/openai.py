import logging
from typing import Optional

from pydantic import BaseModel

from module.network.openai_client import call_json, create_openai_client

logger = logging.getLogger(__name__)


class Episode(BaseModel):
    title_en: Optional[str] = None
    title_zh: Optional[str] = None
    title_jp: Optional[str] = None
    season: str = ""
    season_raw: str = ""
    episode: str = ""
    sub: str = ""
    group: str = ""
    resolution: str = ""
    source: str = ""


DEFAULT_PROMPT = """\
You are an anime torrent name parser. Extract structured data from the given text and return a JSON object with these fields:
- title_en: English official title (null if unknown)
- title_zh: Chinese title (null if unknown)
- title_jp: Japanese title (null if unknown)
- season: Season number, e.g. "1", "2" (empty string if unknown)
- season_raw: Raw season string from text, e.g. "S01", "Season 2" (empty string if unknown)
- episode: Episode number, e.g. "01", "12" (empty string if unknown)
- sub: Subtitle group name (empty string if unknown)
- group: Release group name (empty string if unknown)
- resolution: Video resolution, e.g. "1080p" (empty string if unknown)
- source: Video source, e.g. "WebRip", "BDRip" (empty string if unknown)

If you cannot extract a field, use null for optional fields or empty string for required fields. Do not fabricate data.
"""


class OpenAIParser:
    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        api_type: str = "openai",
        **kwargs,
    ) -> None:
        """OpenAIParser is a class to parse text with openai

        Args:
            api_key (str): the OpenAI api key
            api_base (str):
                the OpenAI api base url, you can use custom url here. \
                Defaults to "https://api.openai.com/v1".
            model (str):
                the ChatGPT model parameter, you can get more details from \
                https://platform.openai.com/docs/api-reference/chat/create. \
                Defaults to "gpt-4o-mini".
            kwargs (dict):
                the OpenAI ChatGPT parameters, you can get more details from \
                https://platform.openai.com/docs/api-reference/chat/create.

        Raises:
            ValueError: if api_key is not provided.
        """
        if not api_key:
            raise ValueError("API key is required.")

        config = dict(
            api_key=api_key,
            api_base=api_base,
            model=model,
            api_type=api_type,
            **kwargs,
        )
        self.client = create_openai_client(config)
        self.model = model
        self.openai_kwargs = kwargs

    def parse(
        self, text: str, prompt: str | None = None, asdict: bool = True
    ) -> dict | str:
        """parse text with openai

        Args:
            text (str): the text to be parsed
            prompt (str | None, optional):
                the custom prompt. Built-in prompt will be used if no prompt is provided. \
                Defaults to None.
            asdict (bool, optional):
                whether to return the result as dict or not. \
                Defaults to True.

        Returns:
            dict | str: the parsed result.
        """
        if not prompt:
            prompt = DEFAULT_PROMPT

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ]

        logger.info("[LLM] 标题解析 | 输入: %s", text[:80])
        result = call_json(
            self.client,
            self.model,
            messages,
            response_model=Episode,
            temperature=0,
        )

        if asdict:
            result = result.model_dump()

        logger.info(
            "[LLM] 标题解析 | 结果: title_en=%s, season=%s, episode=%s, group=%s",
            result.get("title_en"),
            result.get("season"),
            result.get("episode"),
            result.get("group"),
        )
        return result
