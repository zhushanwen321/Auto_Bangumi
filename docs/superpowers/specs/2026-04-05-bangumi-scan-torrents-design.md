# Bangumi Scan Torrents 设计规格

## Context

收集弹窗（Episode Manager）当前从 `torrent` 表读取种子。如果定时任务 `refresh_rss()` 从未成功处理过某个番剧的种子（例如规则添加太晚、种子已被 `check_new()` 过滤），torrent 表为空，弹窗就什么也不显示。用户无法知道哪些种子可用、为什么没被收集。

本设计将收集弹窗改为从 RSS 实时拉取种子，展示匹配详情，并在下载时才写入 torrent 表。

## 需求

1. 弹窗打开时实时从番剧的 RSS 源拉取全部种子
2. 对每个种子执行匹配，展示匹配了哪条规则（title_raw / alias）、是否被 filter 过滤及原因
3. 只显示匹配到当前番剧的种子（downloaded + filtered），未匹配的不显示
4. filtered 的种子显示但不可操作，附带过滤原因
5. scan 不写入 torrent 表；实际下载时才写入
6. 复用已有 `match_torrent_with_details()` 匹配逻辑

## API 设计

### POST /api/v1/bangumi/{bangumi_id}/scan-torrents

实时从 RSS 拉取种子，匹配并返回详情。不写入数据库。需要认证（`Depends(get_current_user)`）。

**请求体**: 无

**响应体**: `ScanTorrentsResponse`

```python
class ScannedTorrent(BaseModel):
    name: str
    url: str
    download_action: str  # "downloaded" | "filtered"  (downloaded = 匹配且符合下载条件，filtered = 匹配但被过滤)
    matched_pattern: Optional[str] = None
    pattern_type: Optional[str] = None  # "title_raw" | "alias"
    filter_reason: Optional[str] = None

class ScanTorrentsResponse(BaseModel):
    report: str  # 匹配报告文本
    torrents: list[ScannedTorrent]
```

### POST /api/v1/bangumi/{bangumi_id}/recollect-by-urls

按种子 URL 列表提交下载。接收 scan 返回的 url，写入 torrent 表并提交下载。需要认证。

**请求体**:
```python
class RecollectByUrlsRequest(BaseModel):
    torrent_urls: list[str]
```

**响应体**: 同现有 recollect（成功/失败消息）

**逻辑**:
1. 从 DB 获取 bangumi
2. 调 `engine.scan_bangumi_torrents(bangumi_id)` 重新获取种子列表
3. 按 url 过滤出请求的种子
4. 对过滤出的种子设置 `torrent.bangumi_id = bangumi.id`
5. 写入 torrent 表
6. 提交下载客户端
7. 更新 `downloaded = True`

**注意**：recollect-by-urls 会重新拉取 RSS 以获取种子完整数据（如 torrent.url、torrent.name 等），因为 scan 端点是无状态的，不在服务端缓存结果。如果两次调用间 RSS 内容变化导致某些 URL 不再存在，这些 URL 会被静默忽略。

## 后端实现

### RSSEngine.scan_bangumi_torrents(bangumi_id)

```python
async def scan_bangumi_torrents(self, bangumi_id: int) -> tuple[list[ScannedTorrent], str]:
    """实时从 RSS 拉取种子，匹配当前番剧，返回详情和报告。"""
```

流程:
1. `self.bangumi.search_id(bangumi_id)` 获取番剧
2. 解析 `bangumi.rss_link`：如果是逗号分隔的多个 URL，逐个拉取并合并结果
3. 调 `RequestContent.get_torrents(rss_url)` 拉取种子 — **不传 filter 参数**，获取所有原始种子（全局默认过滤仍会排除非视频文件，但不会应用番剧的排除规则），这样过滤掉的种子才能在 UI 中展示原因
4. 对每个种子调 `self.match_torrent_with_details(torrent)` 匹配所有番剧
5. 过滤：只保留 `torrent.bangumi_id == bangumi_id` 的种子（`match_torrent_with_details` 在匹配成功时设置此字段）
6. 构建简单报告文本（按 downloaded/filtered 分组列出种子名和匹配原因），不走 MatchCollector.generate_report（因为 MatchCollector 按 RSS 源组织报告，不适合单番剧场景）
7. 返回种子列表 + 报告，不写 DB

### 新增模型文件

ScannedTorrent、ScanTorrentsResponse、RecollectByUrlsRequest 定义在 `backend/src/module/models/torrent.py`（或新建 schema 文件）。

### 文件变更

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/src/module/api/bangumi.py` | 新增 scan-torrents、recollect-by-urls 端点 |
| 修改 | `backend/src/module/rss/engine.py` | 新增 `scan_bangumi_torrents()` 方法 |
| 修改 | `backend/src/module/models/torrent.py` | 新增 ScannedTorrent、ScanTorrentsResponse、RecollectByUrlsRequest |
| 修改 | `webui/src/api/bangumi.ts` | 新增 scanTorrents、recollectByUrls API 调用 |
| 修改 | `webui/types/bangumi.ts` | 新增 ScannedTorrent 接口 |
| 修改 | `webui/src/components/ab-episode-manager.vue` | 改为调 scan API，展示匹配报告 |
| 修改 | `webui/src/i18n/zh-CN.json` | 新增匹配状态文案 |

## 前端改动

### ab-episode-manager.vue

1. `fetchTorrents()` 改为调用 `POST /scan-torrents`
2. 种子按 `download_action` 分组展示：
   - **downloaded**: 正常样式，可勾选，可 recollect（含义是"符合下载条件"，而非"已下载到磁盘"）
   - **filtered**: 灰色样式，不可勾选，显示 `filter_reason`
3. 报告文本展示在弹窗底部（可折叠区域）
4. recollect 按钮传 `torrent_urls`（从 scan 结果中选出的 url）

### 不改动的部分

- `match_torrent_with_details()` — 原样复用
- `MatchCollector` — 不用于 scan 场景（scan 构建自己的简单报告）
- 现有 `GET /{id}/torrents` — 保留
- `refresh_rss()` — 不改动
- 现有 `POST /{id}/recollect` — 保留，新增 recollect-by-urls 端点

## 边界情况

1. **bangumi.rss_link 为空**: 返回空列表 + 报告提示"未配置 RSS 链接"
2. **RSS 拉取失败**: 返回空列表 + 报告包含错误信息
3. **无匹配种子**: 返回空列表 + 报告说明"RSS 中无匹配当前番剧的种子"
4. **recollect 时种子 URL 不在重新拉取结果中**: 静默忽略不存在的 URL
5. **bangumi.rss_link 包含多个逗号分隔 URL**: 逐个拉取，合并结果，去重（按 URL）

## 测试计划

### 后端测试

1. `scan_bangumi_torrents()` — 正常匹配、过滤、无匹配、RSS 失败、多个 RSS 链接
2. scan-torrents API 端点 — 权限、参数验证、响应格式
3. recollect-by-urls API 端点 — 写入 DB、提交下载、URL 不存在时静默忽略

### 前端测试

手动测试：
1. 打开收集弹窗 → 看到种子列表和匹配报告
2. filtered 种子灰色不可选 → 显示原因
3. 勾选 downloaded 种子 → recollect → 下载成功
4. 无匹配种子时显示空状态
