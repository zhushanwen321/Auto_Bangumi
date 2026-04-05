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
