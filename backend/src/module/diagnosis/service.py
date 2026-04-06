from __future__ import annotations

import logging
from collections import defaultdict
from typing import Optional

from module.downloader import DownloadClient
from module.models import Bangumi, Torrent
from module.parser import TitleParser
from module.rss.engine import RSSEngine

from .collector import DiagnosisCollector
from .models import FixAction, PreviewItem

logger = logging.getLogger(__name__)


class DiagnosisService(RSSEngine):
    """RSS 诊断服务：预览、诊断、修复。

    继承 RSSEngine 以复用数据库访问和 match_torrent 逻辑。
    """

    async def preview(self, rss_id: int) -> list[PreviewItem]:
        """快速返回 RSS 下番剧列表供用户选择。

        对每个种子执行 raw_parser 解析，按 title_raw 分组，
        并检查数据库中的匹配状态。
        """
        rss = self.rss.search_id(rss_id)
        if not rss:
            return []

        torrents = await self._get_torrents(rss)

        # 解析所有种子，收集按标题分组的信息
        groups: dict[str, list[Torrent]] = defaultdict(list)
        parse_results: dict[str, Optional[Bangumi]] = {}

        for t in torrents:
            parsed = TitleParser.raw_parser(t.name)
            if parsed and parsed.title_raw:
                groups[parsed.title_raw].append(t)
                parse_results[t.name] = parsed
            else:
                # 解析失败的种子用原始名称分组
                groups[t.name].append(t)
                parse_results[t.name] = None

        # 检查每个种子在数据库中的匹配状态
        matched_titles: set[str] = set()
        matched_ids: dict[str, int] = {}

        for t in torrents:
            db_match = self.bangumi.match_torrent(t.name)
            if db_match:
                parsed = parse_results[t.name]
                key = parsed.title_raw if parsed else t.name
                matched_titles.add(key)
                if key not in matched_ids:
                    matched_ids[key] = db_match.id

        result: list[PreviewItem] = []
        for title, ts in groups.items():
            parsed = parse_results[ts[0].name]
            is_parsed = parsed is not None
            is_matched = title in matched_titles

            if not is_parsed:
                status = "unparsed"
            elif is_matched:
                status = "matched"
            else:
                status = "unmatched"

            result.append(
                PreviewItem(
                    title=title,
                    bangumi_id=matched_ids.get(title),
                    torrent_count=len(ts),
                    status=status,
                )
            )

        return result

    async def diagnose(
        self,
        rss_id: int,
        anime_titles: list[str] | None = None,
    ) -> DiagnosisReport:
        """完整诊断扫描：解析 -> 匹配 -> 过滤 -> (聚合时) 创建状态检查。

        通过 collector 记录每一步结果，最终生成 DiagnosisReport。
        """
        from .models import DiagnosisReport

        rss = self.rss.search_id(rss_id)
        if not rss:
            return DiagnosisReport(rss_id=rss_id, rss_url="", errors=["RSS 不存在"])

        collector = DiagnosisCollector()

        try:
            torrents = await self._get_torrents(rss)
        except Exception as e:
            return DiagnosisReport(
                rss_id=rss_id,
                rss_url=rss.url,
                errors=[f"获取 RSS 种子失败: {e}"],
            )

        for t in torrents:
            # 第一步：解析
            parsed = TitleParser.raw_parser(t.name, collector=collector)
            # 第二步：匹配 + 过滤
            self.match_torrent(t, collector=collector)
            # 第三步：检查下载状态（诊断场景只检查数据库记录）
            if parsed:
                existing = self.torrent.search_rss(rss_id)
                for ext in existing:
                    if ext.name == t.name:
                        collector.record_download(t.name, ext.downloaded)
                        break

        # 聚合 RSS 需要额外检查 bangumi 创建状态
        if rss.aggregate:
            from module.rss.analyser import RSSAnalyser

            analyser = RSSAnalyser()
            await analyser.torrents_to_data(torrents, rss, full_parse=True, collector=collector)

        return collector.build_report(rss_id, rss.url, anime_titles)

    async def fix(self, action: FixAction) -> bool:
        """按 action 分发执行修复操作。"""
        if action.action == "force_download":
            return await self._fix_force_download(action)
        elif action.action == "link_bangumi":
            return self._fix_link_bangumi(action)
        elif action.action == "fix_parse":
            return self._fix_parse(action)
        elif action.action == "edit_filter":
            return self._fix_edit_filter(action)
        else:
            logger.warning("[Diagnosis] Unknown fix action: %s", action.action)
            return False

    async def _fix_force_download(self, action: FixAction) -> bool:
        params = action.params
        torrent_url = params.get("torrent_url", "")
        bangumi_id = params.get("bangumi_id")

        bangumi = self.bangumi.search_id(bangumi_id)
        if not bangumi:
            logger.warning("[Diagnosis] Bangumi %s not found", bangumi_id)
            return False

        torrent = Torrent(name=action.torrent_name, url=torrent_url, bangumi_id=bangumi_id)

        try:
            async with DownloadClient() as client:
                result = await client.add_torrent(torrent, bangumi)
            if result:
                self.torrent.add(torrent)
                self.commit()
            return result
        except Exception as e:
            logger.error("[Diagnosis] Force download failed: %s", e)
            return False

    def _fix_link_bangumi(self, action: FixAction) -> bool:
        params = action.params
        torrent_id = params.get("torrent_id")
        bangumi_id = params.get("bangumi_id")

        torrent = self.torrent.search(torrent_id)
        if not torrent:
            logger.warning("[Diagnosis] Torrent %s not found", torrent_id)
            return False

        bangumi = self.bangumi.search_id(bangumi_id)
        if not bangumi:
            logger.warning("[Diagnosis] Bangumi %s not found", bangumi_id)
            return False

        torrent.bangumi_id = bangumi_id
        self.add(torrent)
        self.commit()
        return True

    def _fix_parse(self, action: FixAction) -> bool:
        params = action.params
        title_raw = params.get("title_raw", action.torrent_name)
        season = params.get("season", 1)

        bangumi = Bangumi(
            official_title=title_raw,
            title_raw=title_raw,
            season=season,
            filter="",
        )
        self.bangumi.add_all([bangumi])
        self.commit()
        return True

    def _fix_edit_filter(self, action: FixAction) -> bool:
        params = action.params
        bangumi_id = params.get("bangumi_id")
        new_filter = params.get("filter", "")

        bangumi = self.bangumi.search_id(bangumi_id)
        if not bangumi:
            logger.warning("[Diagnosis] Bangumi %s not found", bangumi_id)
            return False

        bangumi.filter = new_filter
        self.add(bangumi)
        self.commit()
        return True
