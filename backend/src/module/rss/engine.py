import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from module.database import Database, engine
from module.downloader import DownloadClient
from module.models import Bangumi, ResponseModel, RSSItem, Torrent
from module.network import RequestContent
from module.rss.match_report import MatchCollector, MatchResult

logger = logging.getLogger(__name__)


class RSSEngine(Database):
    def __init__(self, _engine=engine):
        super().__init__(_engine)
        self._to_refresh = False
        self._filter_cache: dict[str, re.Pattern] = {}

    @staticmethod
    async def _get_torrents(rss: RSSItem) -> list[Torrent]:
        async with RequestContent() as req:
            torrents = await req.get_torrents(rss.url)
            # Add RSS ID
            for torrent in torrents:
                torrent.rss_id = rss.id
        return torrents

    def get_rss_torrents(self, rss_id: int) -> list[Torrent]:
        rss = self.rss.search_id(rss_id)
        if rss:
            return self.torrent.search_rss(rss_id)
        else:
            return []

    async def add_rss(
        self,
        rss_link: str,
        name: str | None = None,
        aggregate: bool = True,
        parser: str = "mikan",
    ):
        if not name:
            async with RequestContent() as req:
                name = await req.get_rss_title(rss_link)
                if not name:
                    return ResponseModel(
                        status=False,
                        status_code=406,
                        msg_en="Failed to get RSS title.",
                        msg_zh="无法获取 RSS 标题。",
                    )
        rss_data = RSSItem(name=name, url=rss_link, aggregate=aggregate, parser=parser)
        if self.rss.add(rss_data):
            return ResponseModel(
                status=True,
                status_code=200,
                msg_en="RSS added successfully.",
                msg_zh="RSS 添加成功。",
            )
        else:
            return ResponseModel(
                status=False,
                status_code=406,
                msg_en="RSS added failed.",
                msg_zh="RSS 添加失败。",
            )

    def disable_list(self, rss_id_list: list[int]):
        self.rss.disable_batch(rss_id_list)
        return ResponseModel(
            status=True,
            status_code=200,
            msg_en="Disable RSS successfully.",
            msg_zh="禁用 RSS 成功。",
        )

    def enable_list(self, rss_id_list: list[int]):
        self.rss.enable_batch(rss_id_list)
        return ResponseModel(
            status=True,
            status_code=200,
            msg_en="Enable RSS successfully.",
            msg_zh="启用 RSS 成功。",
        )

    def delete_list(self, rss_id_list: list[int]):
        for rss_id in rss_id_list:
            self.rss.delete(rss_id)
        return ResponseModel(
            status=True,
            status_code=200,
            msg_en="Delete RSS successfully.",
            msg_zh="删除 RSS 成功。",
        )

    async def pull_rss(self, rss_item: RSSItem) -> list[Torrent]:
        torrents = await self._get_torrents(rss_item)
        new_torrents = self.torrent.check_new(torrents)
        return new_torrents

    async def _pull_rss_with_status(
        self, rss_item: RSSItem
    ) -> tuple[list[Torrent], Optional[str]]:
        try:
            torrents = await self.pull_rss(rss_item)
            return torrents, None
        except Exception as e:
            logger.warning(f"[Engine] Failed to fetch RSS {rss_item.name}: {e}")
            return [], str(e)

    async def _pull_rss_with_torrent_counts(
        self, rss_item: RSSItem
    ) -> tuple[list[Torrent], int, int, Optional[str]]:
        """拉取 RSS 种子并返回计数信息。

        Returns:
            (new_torrents, total_count, new_count, error_message)
        """
        try:
            all_torrents = await self._get_torrents(rss_item)
            new_torrents = self.torrent.check_new(all_torrents)
            return new_torrents, len(all_torrents), len(new_torrents), None
        except Exception as e:
            logger.warning(f"[Engine] Failed to fetch RSS {rss_item.name}: {e}")
            return [], 0, 0, str(e)

    def _get_filter_pattern(self, filter_str: str) -> re.Pattern:
        if filter_str not in self._filter_cache:
            raw_pattern = filter_str.replace(",", "|")
            try:
                self._filter_cache[filter_str] = re.compile(
                    raw_pattern, re.IGNORECASE
                )
            except re.error:
                # Filter contains invalid regex chars (e.g. unmatched '[')
                # Fall back to escaping each term for literal matching
                terms = filter_str.split(",")
                escaped = "|".join(re.escape(t) for t in terms)
                self._filter_cache[filter_str] = re.compile(
                    escaped, re.IGNORECASE
                )
                logger.warning(
                    f"[Engine] Filter '{filter_str}' contains invalid regex, "
                    f"using literal matching"
                )
        return self._filter_cache[filter_str]

    def match_torrent(self, torrent: Torrent) -> Optional[Bangumi]:
        matched: Bangumi = self.bangumi.match_torrent(torrent.name)
        if matched:
            if matched.filter == "":
                return matched
            pattern = self._get_filter_pattern(matched.filter)
            if not pattern.search(torrent.name):
                torrent.bangumi_id = matched.id
                return matched
        return None

    def match_torrent_with_details(
        self, torrent: Torrent
    ) -> tuple[Optional[Bangumi], "MatchResult"]:
        """匹配种子并返回详细信息，用于日志记录。

        与 match_torrent() 的 filter 判断逻辑完全一致，额外返回 MatchResult
        记录匹配过程（匹配的 pattern、下载/过滤动作及原因）。

        Returns:
            (Bangumi 或 None, MatchResult) 元组。
            Bangumi 非 None 表示应该下载，None 表示不下载。
        """
        result = self.bangumi.match_torrent_with_pattern(torrent.name)

        if not result:
            return None, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=None,
                download_action="not_matched",
                matched_pattern=None,
                filter_reason=None,
            )

        matched, pattern = result

        # 判断匹配来源是 title_raw 还是 alias
        pattern_type = (
            "title_raw" if pattern == matched.title_raw else "alias"
        )

        # filter 为空，直接下载
        if matched.filter == "":
            torrent.bangumi_id = matched.id
            return matched, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=matched.official_title,
                download_action="downloaded",
                matched_pattern=pattern,
                pattern_type=pattern_type,
                filter_reason=None,
            )

        # filter 是排除规则：search 匹配到说明种子名包含排除关键词
        filter_pattern = self._get_filter_pattern(matched.filter)
        if not filter_pattern.search(torrent.name):
            # 种子名不包含排除关键词，允许下载
            torrent.bangumi_id = matched.id
            return matched, MatchResult(
                torrent_name=torrent.name,
                matched_bangumi=matched.official_title,
                download_action="downloaded",
                matched_pattern=pattern,
                pattern_type=pattern_type,
                filter_reason=None,
            )

        # 种子名包含排除关键词，被过滤
        return None, MatchResult(
            torrent_name=torrent.name,
            matched_bangumi=matched.official_title,
            download_action="filtered",
            matched_pattern=pattern,
            pattern_type=pattern_type,
            filter_reason=f"种子名称匹配 filter 正则 /{matched.filter}/",
        )

    async def refresh_rss(self, client: DownloadClient, rss_id: Optional[int] = None):
        # 获取要处理的 RSS 源
        if not rss_id:
            rss_items: list[RSSItem] = self.rss.search_active()
        else:
            rss_item = self.rss.search_id(rss_id)
            rss_items = [rss_item] if rss_item else []

        logger.debug("[Engine] Get %s RSS items", len(rss_items))

        # 并发拉取所有 RSS 源的种子
        results = await asyncio.gather(
            *[
                self._pull_rss_with_torrent_counts(rss_item)
                for rss_item in rss_items
            ]
        )

        # 初始化 MatchCollector 收集匹配结果
        collector = MatchCollector()
        now = datetime.now(timezone.utc).isoformat()

        # 顺序处理结果（涉及数据库操作）
        for rss_item, (new_torrents, total_count, new_count, error) in zip(
            rss_items, results
        ):
            # 更新 RSS 连接状态
            rss_item.connection_status = "error" if error else "healthy"
            rss_item.last_checked_at = now
            rss_item.last_error = error
            self.add(rss_item)

            # 记录 RSS 源处理开始和种子计数
            collector.start_rss(rss_item)
            collector.set_torrent_counts(rss_item.id, total=total_count, new=new_count)

            for torrent in new_torrents:
                matched_data, match_result = self.match_torrent_with_details(torrent)

                if matched_data:
                    # 匹配成功，尝试添加下载
                    if await client.add_torrent(torrent, matched_data):
                        logger.debug(
                            "[Engine] Add torrent %s to client", torrent.name
                        )
                        torrent.downloaded = True
                    else:
                        # 下载客户端添加失败，修正 action 为 not_added
                        match_result.download_action = "not_added"

                # 无论匹配结果如何，都记录到 collector
                collector.record_match(rss_item.id, match_result)

            collector.finish_rss(rss_item.id)

            # 将所有种子写入数据库
            self.torrent.add_all(new_torrents)

        self.commit()

        # 生成并输出报告
        report = collector.generate_report()
        logger.info(report)

    async def download_bangumi(self, bangumi: Bangumi):
        async with RequestContent() as req:
            torrents = await req.get_torrents(
                bangumi.rss_link, bangumi.filter.replace(",", "|")
            )
            if torrents:
                async with DownloadClient() as client:
                    await client.add_torrent(torrents, bangumi)
                    self.torrent.add_all(torrents)
                    return ResponseModel(
                        status=True,
                        status_code=200,
                        msg_en=f"[Engine] Download {bangumi.official_title} successfully.",
                        msg_zh=f"下载 {bangumi.official_title} 成功。",
                    )
            else:
                return ResponseModel(
                    status=False,
                    status_code=406,
                    msg_en=f"[Engine] Download {bangumi.official_title} failed.",
                    msg_zh=f"[Engine] 下载 {bangumi.official_title} 失败。",
                )
