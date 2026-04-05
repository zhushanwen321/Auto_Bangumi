# RSS 匹配日志增强 - 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RSS 刷新流程中添加详细的匹配日志，记录每个种子的完整匹配链路（匹配 Bangumi、filter 过滤、未匹配原因）。

**Architecture:** 新增 `MatchCollector` 类收集匹配结果，在 `refresh_rss()` 结束后生成结构化报告。修改 `BangumiDatabase` 返回匹配的具体 pattern 名称，修改 `RSSEngine` 集成收集器。

**Tech Stack:** Python 3.10+, dataclasses, SQLModel, logging

**Spec:** `docs/superpowers/specs/2026-04-05-rss-match-logging-design.md`

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新增 | `backend/src/module/rss/match_report.py` | MatchResult/RSSResult 数据结构 + MatchCollector 收集器 + 报告生成 |
| 修改 | `backend/src/module/database/bangumi.py:464-490` | 新增 `match_torrent_with_pattern()` 返回 (Bangumi, pattern) |
| 修改 | `backend/src/module/rss/engine.py:134-173` | 新增 `match_torrent_with_details()` + `refresh_rss()` 集成 MatchCollector |

---

## 执行顺序

按依赖关系严格顺序执行：

```
Module 1 (match_report.py)  ← 无依赖，独立开发
    ↓
Module 2 (bangumi.py)       ← 无依赖，可与 Module 1 并行
    ↓
Module 3 (engine.py)        ← 依赖 Module 1 + Module 2
```

## 模块计划

- [Module 1: 数据结构与报告生成器](module-1-match-report.md) — MatchResult/RSSResult 数据结构 + MatchCollector 收集器 + 报告生成（7 个 Task, ~28 个测试）
- [Module 2: 数据库匹配增强](module-2-bangumi-pattern.md) — 新增 `match_torrent_with_pattern()` 返回匹配的具体 pattern（1 个 Task, 9 个测试）
- [Module 3: 引擎集成](module-3-engine-integration.md) — 新增 `match_torrent_with_details()` + `refresh_rss()` 集成 MatchCollector（5 个 Task, ~24 个测试）
