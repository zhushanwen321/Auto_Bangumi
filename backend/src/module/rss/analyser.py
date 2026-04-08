from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from module.conf import settings
from module.models import Bangumi, ResponseModel, RSSItem, Torrent
from module.network import RequestContent
from module.parser import TitleParser

if TYPE_CHECKING:
    from module.diagnosis.collector import DiagnosisCollector

from .engine import RSSEngine

logger = logging.getLogger(__name__)


class RSSAnalyser(TitleParser):
    async def official_title_parser(self, bangumi: Bangumi, rss: RSSItem, torrent: Torrent):
        title_enhanced = False

        if rss.parser == "mikan":
            try:
                poster_link, official_title = await self.mikan_parser(
                    torrent.homepage
                )
                if official_title:
                    bangumi.official_title = official_title
                if poster_link:
                    bangumi.poster_link = poster_link
                if bangumi.official_title:
                    title_enhanced = True
            except (AttributeError, TypeError):
                logger.warning("[Parser] Mikan torrent has no homepage info.")
        elif rss.parser == "tmdb":
            tmdb_title, season, year, poster_link = await self.tmdb_parser(
                bangumi.official_title, bangumi.season, settings.rss_parser.language
            )
            bangumi.official_title = tmdb_title
            bangumi.year = year
            bangumi.season = season
            bangumi.poster_link = poster_link
            # TMDB search failed when year and poster_link are both None
            if year is not None or poster_link is not None:
                title_enhanced = True
        else:
            pass

        # AI enhanced search: trigger when title was not enhanced
        if settings.experimental_openai.enable and settings.experimental_openai.features.enable_title_enhancement and not title_enhanced:
            from module.searcher.ai_matcher import AIMatcher

            try:
                kwargs = settings.experimental_openai.dict(exclude={"enable", "features"})
                matcher = AIMatcher(openai_config=kwargs)

                async def tmdb_search_fn(keyword: str) -> list[dict]:
                    from module.parser.analyser.tmdb_parser import tmdb_parser
                    result = await tmdb_parser(keyword, settings.rss_parser.language)
                    if result is None:
                        return []
                    return [
                        {
                            "id": result.id,
                            "title": result.title,
                            "original_title": result.original_title,
                        }
                    ]

                def tmdb_formatter(results: list[dict]) -> str:
                    lines = []
                    for i, r in enumerate(results):
                        lines.append(
                            f"{i + 1}. {r['title']} ({r.get('original_title', '')}) "
                            f"[TMDB ID: {r['id']}]"
                        )
                    return "\n".join(lines)

                match = await matcher.search_and_match(
                    title=bangumi.title_raw,
                    search_fn=tmdb_search_fn,
                    result_formatter=tmdb_formatter,
                    dedup_key=lambda x: x["id"],
                )

                if match and match.confidence >= 0.7:
                    bangumi.official_title = match.matched_item["title"]
                    logger.info(
                        "[AI] Enhanced search matched: %s (confidence=%.2f)",
                        bangumi.official_title,
                        match.confidence,
                    )
            except Exception as e:
                logger.warning("[AI] Enhanced search failed: %s", e)

        if bangumi.official_title:
            bangumi.official_title = re.sub(r"[/:.\\]", " ", bangumi.official_title)

    @staticmethod
    async def get_rss_torrents(rss_link: str, full_parse: bool = True) -> list[Torrent]:
        async with RequestContent() as req:
            if full_parse:
                rss_torrents = await req.get_torrents(rss_link)
            else:
                rss_torrents = await req.get_torrents(rss_link, "\\d+-\\d+")
        return rss_torrents

    async def torrents_to_data(
        self,
        torrents: list[Torrent],
        rss: RSSItem,
        full_parse: bool = True,
        collector: DiagnosisCollector | None = None,
    ) -> list:
        new_data = []
        seen_titles: set[str] = set()
        for torrent in torrents:
            bangumi = self.raw_parser(raw=torrent.name, collector=collector)
            if bangumi and bangumi.title_raw not in seen_titles:
                await self.official_title_parser(bangumi=bangumi, rss=rss, torrent=torrent)
                if collector:
                    collector.record_bangumi_create(torrent.name, bangumi)
                if not full_parse:
                    return [bangumi]
                seen_titles.add(bangumi.title_raw)
                new_data.append(bangumi)
                logger.info(f"[RSS] New bangumi founded: {bangumi.official_title}")
        return new_data

    async def torrent_to_data(self, torrent: Torrent, rss: RSSItem) -> Bangumi:
        bangumi = self.raw_parser(raw=torrent.name)
        if bangumi:
            await self.official_title_parser(bangumi=bangumi, rss=rss, torrent=torrent)
            bangumi.rss_link = rss.url
            return bangumi

    async def rss_to_data(
        self, rss: RSSItem, engine: RSSEngine, full_parse: bool = True
    ) -> list[Bangumi]:
        rss_torrents = await self.get_rss_torrents(rss.url, full_parse)
        torrents_to_add = engine.bangumi.match_list(rss_torrents, rss.url)
        if not torrents_to_add:
            logger.debug("[RSS] No new title has been found.")
            return []
        # New List
        new_data = await self.torrents_to_data(torrents_to_add, rss, full_parse)
        if new_data:
            # Add to database
            engine.bangumi.add_all(new_data)
            # 创建后触发弹弹 Play 番名获取
            self._fetch_dandanplay_titles(new_data)
            return new_data
        else:
            return []

    @staticmethod
    def _fetch_dandanplay_titles(bangumi_list: list[Bangumi]):
        """后台获取弹弹 Play 番名（非阻塞）。"""
        try:
            if settings.bangumi_manage.rename_method not in (
                "dandanplay",
                "subtitle_dandanplay",
            ):
                return
            import asyncio
            from module.searcher.dandanplay import (
                batch_update_dandanplay_titles,
                batch_update_dandanplay_titles_ai,
            )

            # 提取简单数据避免 ORM 对象 detach 问题
            record_data = [
                {"id": b.id, "official_title": b.official_title} for b in bangumi_list
            ]

            use_ai = (
                settings.experimental_openai.enable
                and settings.experimental_openai.features.enable_dandanplay_match
            )

            async def _do_fetch():
                if use_ai:
                    openai_config = settings.experimental_openai.dict(
                        exclude={"enable", "features"}
                    )
                    await batch_update_dandanplay_titles_ai(
                        records=record_data,
                        app_id=settings.dandanplay.app_id,
                        app_secret=settings.dandanplay.app_secret,
                        openai_config=openai_config,
                    )
                else:
                    await batch_update_dandanplay_titles(
                        records=record_data,
                        app_id=settings.dandanplay.app_id,
                        app_secret=settings.dandanplay.app_secret,
                    )

            asyncio.create_task(_do_fetch())
        except Exception as e:
            logger.debug("[RSS] Dandanplay title fetch skipped: %s", e)

    async def link_to_data(self, rss: RSSItem) -> Bangumi | ResponseModel:
        torrents = await self.get_rss_torrents(rss.url, False)
        if not torrents:
            return ResponseModel(
                status=False,
                status_code=406,
                msg_en="Cannot find any torrent.",
                msg_zh="无法找到种子。",
            )
        for torrent in torrents:
            data = await self.torrent_to_data(torrent, rss)
            if data:
                return data
        return ResponseModel(
            status=False,
            status_code=406,
            msg_en="Cannot parse this link.",
            msg_zh="无法解析此链接。",
        )
