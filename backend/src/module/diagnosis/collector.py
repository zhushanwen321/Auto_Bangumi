from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from module.models import Bangumi

from .models import (
    AnimeDiagnosis,
    DiagnosisIssue,
    DiagnosisReport,
    TorrentDiagnosis,
)

# 解析失败的种子归入此分组
_UNPARSED_KEY = "[unparsed]"


@dataclass
class _TorrentRecord:
    torrent_name: str
    parse_result: Optional[Bangumi] = None
    match_result: Optional[Bangumi] = None
    filter_passed: Optional[bool] = None
    filter_reason: Optional[str] = None
    downloaded: bool = False
    _download_recorded: bool = False
    bangumi_created: bool = False
    bangumi_create_error: Optional[str] = None


class DiagnosisCollector:
    """注入式诊断信息收集器。

    在解析/匹配函数中作为可选参数传入，记录每一步的结果。
    正常流程不传（None），诊断流程传入实例。
    """

    def __init__(self) -> None:
        self._records: dict[str, _TorrentRecord] = {}

    def _get_or_create(self, name: str) -> _TorrentRecord:
        if name not in self._records:
            self._records[name] = _TorrentRecord(torrent_name=name)
        return self._records[name]

    def record_parse(self, name: str, result: Optional[Bangumi]) -> None:
        self._get_or_create(name).parse_result = result

    def record_match_result(
        self,
        name: str,
        matched: Optional[Bangumi],
        filter_passed: Optional[bool],
        filter_reason: Optional[str],
    ) -> None:
        rec = self._get_or_create(name)
        rec.match_result = matched
        rec.filter_passed = filter_passed
        rec.filter_reason = filter_reason

    def record_download(self, name: str, downloaded: bool) -> None:
        rec = self._get_or_create(name)
        rec.downloaded = downloaded
        rec._download_recorded = True

    def record_bangumi_create(
        self,
        name: str,
        bangumi: Optional[Bangumi],
        error: Optional[str] = None,
    ) -> None:
        rec = self._get_or_create(name)
        rec.bangumi_created = bangumi is not None
        rec.bangumi_create_error = error

    def build_report(
        self,
        rss_id: int,
        rss_url: str,
        anime_titles: Optional[list[str]] = None,
    ) -> DiagnosisReport:
        # 按 parse_result.title_raw 分组
        groups: dict[str, list[_TorrentRecord]] = defaultdict(list)
        for rec in self._records.values():
            key = rec.parse_result.title_raw if rec.parse_result else _UNPARSED_KEY
            groups[key].append(rec)

        # anime_titles 过滤
        if anime_titles is not None:
            groups = {
                k: v for k, v in groups.items() if k in anime_titles
            }

        anime_list: list[AnimeDiagnosis] = []
        for title, recs in groups.items():
            issues: list[DiagnosisIssue] = []
            bangumi_id: Optional[int] = None

            for rec in recs:
                # 取第一个有效的 match_result id
                if rec.match_result and rec.match_result.id:
                    bangumi_id = rec.match_result.id
                    break

            for rec in recs:
                if rec.parse_result is None:
                    issues.append(
                        DiagnosisIssue("parse", "error", "无法解析种子标题")
                    )
                if rec.bangumi_create_error is not None:
                    issues.append(
                        DiagnosisIssue(
                            "bangumi_create", "warning", rec.bangumi_create_error
                        )
                    )
                if rec.parse_result is not None and rec.match_result is None:
                    issues.append(
                        DiagnosisIssue("match", "warning", "未匹配到任何番剧规则")
                    )
                if rec.filter_passed is False:
                    issues.append(
                        DiagnosisIssue(
                            "filter",
                            "warning",
                            f"被过滤规则排除: {rec.filter_reason}",
                        )
                    )
                if (
                    rec.parse_result is not None
                    and rec.match_result is not None
                    and rec._download_recorded
                    and not rec.downloaded
                ):
                    issues.append(
                        DiagnosisIssue("download", "error", "已匹配但未下载")
                    )

            # 去重（同一步骤同级别的 issue 不重复）
            seen = set()
            unique_issues: list[DiagnosisIssue] = []
            for issue in issues:
                key = (issue.step, issue.severity, issue.message)
                if key not in seen:
                    seen.add(key)
                    unique_issues.append(issue)

            # 判定状态
            has_error = any(i.severity == "error" for i in unique_issues)
            has_warning = any(i.severity == "warning" for i in unique_issues)
            if has_error:
                status = "error"
            elif has_warning:
                status = "warning"
            else:
                status = "ok"

            torrents = [
                TorrentDiagnosis(
                    torrent_name=rec.torrent_name,
                    parse_result=rec.parse_result,
                    match_result=rec.match_result,
                    filter_passed=rec.filter_passed,
                    filter_reason=rec.filter_reason,
                    downloaded=rec.downloaded,
                    issues=[
                        i
                        for i in unique_issues
                        if i.step == "download"
                        and rec._download_recorded
                        and not rec.downloaded
                    ],
                )
                for rec in recs
            ]

            anime_list.append(
                AnimeDiagnosis(
                    anime_title=title,
                    bangumi_id=bangumi_id,
                    status=status,
                    torrents=torrents,
                    fix_actions=[],
                )
            )

        return DiagnosisReport(
            rss_id=rss_id,
            rss_url=rss_url,
            anime_list=anime_list,
        )
