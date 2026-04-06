from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from module.models import Bangumi


@dataclass
class DiagnosisIssue:
    step: str       # "parse" | "bangumi_create" | "match" | "filter" | "download"
    severity: str   # "warning" | "error"
    message: str


@dataclass
class TorrentDiagnosis:
    torrent_name: str
    parse_result: Optional[Bangumi] = None
    match_result: Optional[Bangumi] = None
    # filter 是排除过滤器: True=种子没被排除, None=不涉及过滤
    filter_passed: Optional[bool] = None
    filter_reason: Optional[str] = None
    downloaded: bool = False
    issues: list[DiagnosisIssue] = field(default_factory=list)


@dataclass
class FixAction:
    action: str     # "force_download" | "link_bangumi" | "fix_parse" | "edit_filter"
    torrent_name: str
    params: dict = field(default_factory=dict)


@dataclass
class AnimeDiagnosis:
    anime_title: str
    bangumi_id: Optional[int] = None
    status: str = "ok"  # "ok" | "warning" | "error"
    torrents: list[TorrentDiagnosis] = field(default_factory=list)
    fix_actions: list[FixAction] = field(default_factory=list)


@dataclass
class DiagnosisReport:
    rss_id: int
    rss_url: str
    scanned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    anime_list: list[AnimeDiagnosis] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class PreviewItem:
    title: str
    bangumi_id: Optional[int] = None
    torrent_count: int = 0
    status: str = "unmatched"  # "matched" | "unmatched" | "unparsed"
