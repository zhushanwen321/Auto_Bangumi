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

    def generate_report(self) -> str:
        """生成完整的日志报告。

        Returns:
            结构化的多行文本报告。
        """
        lines: list[str] = ["========== RSS 刷新报告 =========="]
        lines.append(f"处理了 {len(self.rss_results)} 个 RSS 源")

        total_downloaded = 0
        total_filtered = 0
        total_not_matched = 0
        total_not_added = 0

        for rss_id in self.rss_results:
            rss = self.rss_results[rss_id]
            lines.append("")
            lines.append(f"--- 源: {rss.rss_name} ---")
            lines.append(
                f"获取 {rss.total_torrents} 个种子，"
                f"其中 {rss.new_torrents} 个新种子"
            )

            # 按四种 action 分组
            downloaded = [m for m in rss.matches if m.download_action == "downloaded"]
            filtered = [m for m in rss.matches if m.download_action == "filtered"]
            not_matched = [m for m in rss.matches if m.download_action == "not_matched"]
            not_added = [m for m in rss.matches if m.download_action == "not_added"]

            total_downloaded += len(downloaded)
            total_filtered += len(filtered)
            total_not_matched += len(not_matched)
            total_not_added += len(not_added)

            self._append_downloaded_section(lines, downloaded)
            self._append_filtered_section(lines, filtered)
            self._append_not_matched_section(lines, not_matched)
            self._append_not_added_section(lines, not_added)

        # 汇总
        total_new = total_downloaded + total_filtered + total_not_matched + total_not_added
        if total_new > 0:
            lines.append("")
            lines.append(
                f"汇总: {total_new} 个新种子 -> "
                f"{total_downloaded} 个下载, "
                f"{total_filtered} 个过滤, "
                f"{total_not_matched} 个未匹配, "
                f"{total_not_added} 个未订阅"
            )
        lines.append("=================================")
        return "\n".join(lines)

    @staticmethod
    def _group_by_bangumi(matches: list[MatchResult]) -> dict[str, list[MatchResult]]:
        """按 matched_bangumi 分组，保持插入顺序。"""
        groups: dict[str, list[MatchResult]] = {}
        for m in matches:
            key = m.matched_bangumi or "__none__"
            groups.setdefault(key, []).append(m)
        return groups

    def _append_downloaded_section(
        self, lines: list[str], matches: list[MatchResult]
    ) -> None:
        """追加 [下载] 分类。"""
        if not matches:
            return
        lines.append(f"\n[下载] 成功下载 ({len(matches)} 个):")
        for bangumi_name, group in self._group_by_bangumi(matches).items():
            lines.append(f"  {bangumi_name}:")
            for m in group:
                lines.append(f"    + {m.torrent_name}")
                lines.append(f"      匹配: title_raw=\"{m.matched_pattern}\"")

    def _append_filtered_section(
        self, lines: list[str], matches: list[MatchResult]
    ) -> None:
        """追加 [过滤] 分类。"""
        if not matches:
            return
        lines.append(f"\n[过滤] 匹配但被过滤 ({len(matches)} 个):")
        for bangumi_name, group in self._group_by_bangumi(matches).items():
            lines.append(f"  {bangumi_name}:")
            for m in group:
                lines.append(f"    - {m.torrent_name}")
                lines.append(f"      匹配: alias=\"{m.matched_pattern}\"")
                if m.filter_reason:
                    lines.append(f"      原因: {m.filter_reason}")

    def _append_not_matched_section(
        self, lines: list[str], matches: list[MatchResult]
    ) -> None:
        """追加 [未匹配] 分类。"""
        if not matches:
            return
        lines.append(f"\n[未匹配] 未匹配任何 Bangumi ({len(matches)} 个):")
        for m in matches:
            lines.append(f"    - {m.torrent_name}")

    def _append_not_added_section(
        self, lines: list[str], matches: list[MatchResult]
    ) -> None:
        """追加 [未订阅] 分类。"""
        if not matches:
            return
        lines.append(f"\n[未订阅] 已匹配但未添加下载 ({len(matches)} 个):")
        for bangumi_name, group in self._group_by_bangumi(matches).items():
            lines.append(f"  {bangumi_name}:")
            for m in group:
                lines.append(f"    x {m.torrent_name}")
                lines.append(f"      原因: Bangumi 的 added=False")
