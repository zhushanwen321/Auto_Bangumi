# Bangumi Scan Torrents 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将收集弹窗从读取 torrent 表改为实时 RSS 扫描，展示匹配详情和过滤原因，下载时才写入 torrent 表。

**Architecture:** 新增 scan-torrents 端点实时拉取 RSS 种子，匹配后返回详情；新增 recollect-by-urls 端点接收用户选择的种子 URL 并提交下载。前端 Episode Manager 组件改为调用 scan API，按 downloaded/filtered 分类展示种子。

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontend)

---

## 模块索引

| 模块 | 文档 | 任务数 | 说明 |
|------|------|--------|------|
| 后端 | [module-backend-scan-torrents.md](module-scan-torrents-backend.md) | 4 | 模型、Engine 方法、API 端点 |
| 前端 | [module-frontend-scan-torrents.md](module-scan-torrents-frontend.md) | 5 | 类型、API 客户端、i18n、Vue 组件 |

---

## 执行顺序

后端和前端可以并行开发，但前端 Task 4（Vue 组件）依赖后端完成。

```
Phase 1 (并行):
  后端 Task 1-2 ────────── 前端 Task 1-3
  (模型 + Engine)           (类型 + API + i18n)

Phase 2 (并行):
  后端 Task 3-4 ────────── 前端 Task 4
  (API 端点)                (Vue 组件，需后端可用)

Phase 3:
  集成测试
```

---

## 关键决策

1. **scan 不传 filter**: `get_torrents(rss_url)` 不传 filter 参数，获取所有原始种子。番剧的 filter 排除规则由 `match_torrent_with_details()` 应用，确保被过滤的种子能在 UI 中展示原因。

2. **按 bangumi_id 过滤**: 使用 `torrent.bangumi_id == bangumi_id`（int 比较）而非字符串比较，避免 Unicode/大小写问题。

3. **recollect 无状态设计**: 不缓存 scan 结果，recollect 时重新拉取 RSS。如果 URL 已不存在则静默忽略。

4. **不走 MatchCollector.generate_report**: scan 是单番剧场景，MatchCollector 按 RSS 源组织报告不适合。自行构建简单的 downloaded/filtered 分组报告。

5. **选择模型改为 URL**: 前端选择标识从 `Set<number>` (torrent ID) 改为 `Set<string>` (torrent URL)，因为 scan 结果不写入数据库，没有 ID。

---

## 文件变更总览

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/src/module/models/torrent.py` | 新增 ScannedTorrent, ScanTorrentsResponse, RecollectByUrlsRequest |
| 修改 | `backend/src/module/models/__init__.py` | 导出新模型 |
| 修改 | `backend/src/module/rss/engine.py` | 新增 scan_bangumi_torrents(), _build_scan_report() |
| 修改 | `backend/src/module/api/bangumi.py` | 新增 scan-torrents, recollect-by-urls 端点 |
| 新增 | `backend/src/test/test_scan_torrents.py` | 全部后端测试（24 个） |
| 修改 | `webui/types/bangumi.ts` | 新增 ScannedTorrent, ScanTorrentsResponse |
| 修改 | `webui/src/api/bangumi.ts` | 新增 scanTorrents(), recollectByUrls() |
| 修改 | `webui/src/i18n/zh-CN.json` | 更新 episode_manager i18n 键 |
| 修改 | `webui/src/components/ab-episode-manager.vue` | 重写为使用 scan API |

---

## 不改动的部分

- `match_torrent_with_details()` — 原样复用
- `MatchCollector` — 不用于 scan 场景
- 现有 `GET /{id}/torrents` — 保留
- 现有 `POST /{id}/recollect` — 保留
- `refresh_rss()` — 不改动
