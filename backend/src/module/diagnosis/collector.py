from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from module.models import Bangumi

from .models import (
    AnimeDiagnosis,
    DiagnosisIssue,
    DiagnosisReport,
    FixAction,
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
                    issues=_torrent_issues(rec),
                )
                for rec in recs
            ]

            # 根据 issues 生成修复建议
            fix_actions = _build_fix_actions(title, recs, unique_issues)

            anime_list.append(
                AnimeDiagnosis(
                    anime_title=title,
                    bangumi_id=bangumi_id,
                    status=status,
                    torrents=torrents,
                    fix_actions=fix_actions,
                )
            )

        return DiagnosisReport(
            rss_id=rss_id,
            rss_url=rss_url,
            anime_list=anime_list,
        )


def _torrent_issues(
    rec: _TorrentRecord,
) -> list[DiagnosisIssue]:
    """根据种子记录生成该种子的诊断 issues。"""
    result: list[DiagnosisIssue] = []

    # 种子自身的解析失败
    if rec.parse_result is None:
        result.append(DiagnosisIssue("parse", "error", "无法解析种子标题"))

    # 种子未匹配
    if rec.parse_result is not None and rec.match_result is None:
        result.append(DiagnosisIssue("match", "warning", "未匹配到任何番剧规则"))

    # 种子被过滤
    if rec.filter_passed is False:
        result.append(
            DiagnosisIssue(
                "filter", "warning", f"被过滤规则排除: {rec.filter_reason}"
            )
        )

    # bangumi 创建失败
    if rec.bangumi_create_error is not None:
        result.append(
            DiagnosisIssue("bangumi_create", "warning", rec.bangumi_create_error)
        )

    # 已匹配但未下载
    if (
        rec.parse_result is not None
        and rec.match_result is not None
        and rec._download_recorded
        and not rec.downloaded
    ):
        result.append(DiagnosisIssue("download", "error", "已匹配但未下载"))

    return result


def _build_fix_actions(
    title: str,
    recs: list[_TorrentRecord],
    issues: list[DiagnosisIssue],
) -> list[FixAction]:
    """根据诊断问题生成修复建议。"""
    actions: list[FixAction] = []
    issue_steps = {i.step for i in issues}

    # 解析失败 → 为每个解析失败的种子生成修复建议
    if "parse" in issue_steps:
        for rec in recs:
            if rec.parse_result is None:
                actions.append(
                    FixAction(
                        action="fix_parse",
                        torrent_name=rec.torrent_name,
                        params={"reason": "标题解析失败，可手动指定 title_raw 和 season"},
                    )
                )

    # 未匹配 → 建议搜索添加番剧或手动关联
    if "match" in issue_steps:
        first_unmatched = next(
            (r for r in recs if r.parse_result and r.match_result is None), None
        )
        if first_unmatched and first_unmatched.parse_result:
            parsed = first_unmatched.parse_result
            actions.append(
                FixAction(
                    action="link_bangumi",
                    torrent_name=first_unmatched.torrent_name,
                    params={
                        "suggested_title": parsed.official_title or parsed.title_raw,
                        "season": parsed.season,
                        "reason": "数据库中无匹配的番剧规则，可通过搜索添加或手动关联",
                    },
                )
            )

    # 被过滤 → 建议修改过滤规则
    if "filter" in issue_steps:
        first_filtered = next(
            (r for r in recs if r.filter_passed is False), None
        )
        if first_filtered and first_filtered.match_result:
            actions.append(
                FixAction(
                    action="edit_filter",
                    torrent_name=first_filtered.torrent_name,
                    params={
                        "bangumi_id": first_filtered.match_result.id,
                        "current_filter": first_filtered.match_result.filter,
                        "filter_reason": first_filtered.filter_reason,
                        "reason": "种子被该番剧的过滤规则排除，可调整过滤条件",
                    },
                )
            )

    # 已匹配但未下载 → 建议强制下载
    if "download" in issue_steps:
        first_dl_fail = next(
            (
                r
                for r in recs
                if r.parse_result
                and r.match_result
                and r._download_recorded
                and not r.downloaded
            ),
            None,
        )
        if first_dl_fail and first_dl_fail.match_result:
            actions.append(
                FixAction(
                    action="force_download",
                    torrent_name=first_dl_fail.torrent_name,
                    params={
                        "bangumi_id": first_dl_fail.match_result.id,
                        "reason": "种子已匹配但未下载，可尝试强制下载",
                    },
                )
            )

    return actions
