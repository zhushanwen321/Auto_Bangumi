"""RSS 匹配结果收集与报告生成。

在 RSS 刷新流程中，MatchCollector 收集每个种子的匹配结果，
最终生成结构化的文本报告，用于日志输出和问题排查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MatchResult:
    """单个种子的匹配结果。"""

    torrent_name: str
    matched_bangumi: Optional[str] = None  # 匹配到的番剧显示名（如 "推しの子 (S1)"）
    download_action: str = "not_matched"  # downloaded / filtered / not_matched / not_added
    matched_pattern: Optional[str] = None  # 匹配的具体 title_raw 或 alias
    filter_reason: Optional[str] = None  # 过滤原因（仅 filtered 时有值）


@dataclass
class RSSResult:
    """单个 RSS 源的处理结果。"""

    rss_name: str
    rss_id: int
    total_torrents: int = 0
    new_torrents: int = 0
    matches: list[MatchResult] = field(default_factory=list)


class MatchCollector:
    """收集 RSS 刷新过程中的匹配结果，生成详细报告。

    使用方式:
        collector = MatchCollector()
        collector.start_rss(rss_item)
        collector.set_torrent_counts(rss_item.id, total=50, new=12)
        for torrent in new_torrents:
            collector.record_match(rss_item.id, match_result)
        collector.finish_rss(rss_item.id)
        report = collector.generate_report()
    """

    def __init__(self) -> None:
        self.rss_results: dict[int, RSSResult] = {}

    def start_rss(self, rss: object) -> None:
        """开始处理一个 RSS 源。

        Args:
            rss: 任何具有 id 和 name 属性的对象（RSSItem 或测试替身）。
        """
        rss_id = rss.id
        if rss_id not in self.rss_results:
            self.rss_results[rss_id] = RSSResult(
                rss_name=rss.name,
                rss_id=rss_id,
            )

    def set_torrent_counts(self, rss_id: int, total: int, new: int) -> None:
        """设置种子获取/新增计数。

        Args:
            rss_id: RSS 源 ID。
            total: 从 RSS 获取的种子总数。
            new: 其中新增的种子数量。
        """
        self._require_rss(rss_id)
        self.rss_results[rss_id].total_torrents = total
        self.rss_results[rss_id].new_torrents = new

    def record_match(self, rss_id: int, result: MatchResult) -> None:
        """记录单个种子的匹配结果。

        Args:
            rss_id: RSS 源 ID。
            result: 匹配结果。
        """
        self._require_rss(rss_id)
        self.rss_results[rss_id].matches.append(result)

    def finish_rss(self, rss_id: int) -> None:
        """完成处理一个 RSS 源。当前为占位方法，预留扩展空间。"""
        self._require_rss(rss_id)

    def _require_rss(self, rss_id: int) -> None:
        """检查 RSS 源已注册，否则抛出 KeyError。"""
        if rss_id not in self.rss_results:
            raise KeyError(
                f"RSS id={rss_id} 尚未通过 start_rss() 注册"
            )
