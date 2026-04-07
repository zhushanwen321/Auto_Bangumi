import base64
import hashlib
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dandanplay.net"


def generate_signature(
    app_id: str, timestamp: int, path: str, app_secret: str
) -> str:
    data = f"{app_id}{timestamp}{path}{app_secret}"
    sha256_hash = hashlib.sha256(data.encode()).digest()
    return base64.b64encode(sha256_hash).decode()


class DandanplayClient:
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

    def _build_headers(self, path: str) -> dict[str, str]:
        timestamp = int(time.time())
        signature = generate_signature(
            self.app_id, timestamp, path, self.app_secret
        )
        return {
            "X-AppId": self.app_id,
            "X-Timestamp": str(timestamp),
            "X-Signature": signature,
        }

    async def search(self, keyword: str) -> Optional[str]:
        """搜索番剧，返回第一个匹配的 animeTitle，无结果返回 None。"""
        path = "/api/v2/search/anime"
        headers = self._build_headers(path)
        url = f"{BASE_URL}{path}"
        params = {"keyword": keyword, "withRelated": "false"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code != 200:
                    logger.warning(
                        "[Dandanplay] Search failed with status %d for: %s",
                        resp.status_code,
                        keyword,
                    )
                    return None

                data = resp.json()
                animes = data.get("animes", [])
                if animes:
                    return animes[0].get("animeTitle")

                return None
        except httpx.HTTPError as e:
            logger.warning("[Dandanplay] HTTP error for '%s': %s", keyword, e)
            return None


async def fetch_dandanplay_title(
    official_title: str, app_id: str, app_secret: str
) -> Optional[str]:
    """用官方标题搜索弹弹 Play，返回匹配的番名。"""
    if not official_title or not app_id:
        return None
    client = DandanplayClient(app_id=app_id, app_secret=app_secret)
    return await client.search(official_title)


async def batch_update_dandanplay_titles(
    records: list, app_id: str, app_secret: str
):
    """批量更新弹弹 Play 番名。内部管理数据库 session。"""
    from module.database import Database

    client = DandanplayClient(app_id=app_id, app_secret=app_secret)
    for record in records:
        record_id = record.id if hasattr(record, "id") else record["id"]
        official_title = (
            record.official_title
            if hasattr(record, "official_title")
            else record["official_title"]
        )
        try:
            title = await client.search(official_title)
            with Database() as db:
                db.bangumi.update_dandanplay_title(record_id, title)
            if title:
                logger.info(
                    "[Dandanplay] Matched '%s' → '%s'",
                    official_title,
                    title,
                )
            else:
                logger.debug("[Dandanplay] No match for '%s'", official_title)
        except Exception as e:
            logger.warning("[Dandanplay] Error updating '%s': %s", official_title, e)
            with Database() as db:
                db.bangumi.update_dandanplay_title(record_id, None)
