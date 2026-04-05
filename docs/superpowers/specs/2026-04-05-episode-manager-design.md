# 集数管理功能设计文档

## 概述

为已订阅的番剧提供"集数管理"能力，用户可以查看某一规则下所有已知种子的下载状态，并选择性地重新收集下载缺失的集数。

## 背景

当前系统在订阅新番后，`eps_collect` 被立即标记为 `True`。如果当时 RSS 只覆盖了最近几集，历史集数就永远丢失。用户无法通过 UI 补全缺失的历史集数。

## 用户需求

1. 在番剧编辑弹框中新增"集数管理"入口
2. 展示当前规则下所有已知种子的下载状态
3. 默认选中所有未下载的种子，一键重新收集

## 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 数据来源 | 仅数据库已有记录 | 用户选择，简单可靠 |
| 规则范围 | 仅当前规则的种子 (bangumi_id) | 用户选择，避免混淆 |
| 触发方式 | 编辑弹框内新增按钮 | 用户选择，不改变卡片点击行为 |
| 重下行为 | 直接下载，不二次确认 | 用户选择，快捷操作 |
| 种子 URL | 复用数据库中已有的 URL | 用户选择，稳定可预期 |
| 下载状态 | 三态：已下载/下载中/未下载 | 结合数据库 downloaded + qb_hash 映射 qBittorrent 状态 |

## 前端设计

### 入口

在 `ab-edit-rule.vue` 编辑弹框的 footer 区域，归档按钮之前新增「集数管理」按钮。点击后关闭编辑弹框，打开独立的集数管理 Modal。

### 集数管理弹框

```
┌─────────────────────────────────────────┐
│ 集数管理                          [✕]    │
│ 葬送的芙莉莲 Season 1 · 桜都字幕组       │
├─────────────────────────────────────────┤
│ [☑] 全选              已选 3/8 项        │
├─────────────────────────────────────────┤
│ ☐  [桜都字幕组] 葬送的芙莉莲 - 01  已下载 │
│ ☐  [桜都字幕组] 葬送的芙莉莲 - 02  已下载 │
│ ☑  [桜都字幕组] 葬送的芙莉莲 - 03  未下载 │  ← 高亮背景
│ ☑  [桜都字幕组] 葬送的芙莉莲 - 04  下载中 │  ← 高亮背景
│ ☑  [桜都字幕组] 葬送的芙莉莲 - 05  未下载 │  ← 高亮背景
│ ☐  [桜都字幕组] 葬送的芙莉莲 - 06  已下载 │
│ ☑  [桜都字幕组] 葬送的芙莉莲 - 07  未下载 │  ← 高亮背景
│ ☐  [桜都字幕组] 葬送的芙莉莲 - 08  已下载 │
├─────────────────────────────────────────┤
│ 共 8 集，已下载 4 集    [重新收集下载(3)] │
└─────────────────────────────────────────┘
```

#### 布局规范

- 全屏高度弹框，通过 `<Teleport to="body">` 渲染
- 最大宽度 480px（与编辑弹框一致）
- 可滚动列表区域，行高适配触摸操作

#### 状态标签颜色

| 状态 | 背景色 | 文字色 | 判定逻辑 |
|------|--------|--------|----------|
| 已下载 | `#dcfce7` | `#16a34a` | `downloaded=True` |
| 下载中 | `#dbeafe` | `#2563eb` | `downloaded=False` 且 `qb_hash` 存在且 qBittorrent 状态为 downloading |
| 未下载 | `#fef3c7` | `#d97706` | `downloaded=False` 且无 `qb_hash` 或 qBittorrent 中无此种子 |

#### 交互行为

1. 打开时默认选中所有「未下载」状态的行，已选中行显示高亮背景
2. 全选/取消全选控制所有行的选中状态
3. 底部按钮显示当前选中数量 `(N)`
4. 点击「重新收集下载」后直接调用 API，显示 loading 状态
5. 成功后关闭弹框并显示 toast 提示

### 新增文件

- `webui/src/components/ab-episode-manager.vue` — 集数管理弹框组件

### 修改文件

- `webui/src/components/ab-edit-rule.vue` — footer 中新增「集数管理」按钮
- `webui/src/api/bangumi.ts` — 新增 `getTorrents(id)` 和 `recollectTorrents(id, torrentIds)` API 函数
- `webui/src/store/bangumi.ts` — 新增 `openEpisodeManager` 方法
- `webui/src/i18n/` — 新增集数管理相关翻译

## 后端设计

### 新增 API 端点

#### 1. 获取番剧种子列表

```
GET /api/v1/bangumi/{bangumi_id}/torrents
```

**响应**: `list[TorrentDetail]`

```python
class TorrentDetail(BaseModel):
    id: int
    name: str
    url: str
    downloaded: bool
    status: str  # "downloaded" | "downloading" | "not_downloaded"
```

**逻辑**:
1. 查询 `torrent` 表中 `bangumi_id == bangumi_id` 的所有记录
2. 收集所有 `qb_hash` 不为空的记录
3. 批量查询 qBittorrent 的种子状态 (`torrents_info`)
4. 映射状态：
   - `downloaded=True` → `"downloaded"`
   - `downloaded=False` + `qb_hash` 存在且 qBittorrent 中状态为 uploading/downloading/stalledDL → `"downloading"`
   - 其他 → `"not_downloaded"`

#### 2. 重新收集下载

```
POST /api/v1/bangumi/{bangumi_id}/recollect
```

**请求体**:

```python
class RecollectRequest(BaseModel):
    torrent_ids: list[int]
```

**响应**: `APIResponse`

**逻辑**:
1. 根据 `torrent_ids` 从数据库查询 torrent 记录
2. 验证所有 torrent 的 `bangumi_id` 匹配，不匹配时返回 400 Bad Request，响应体包含 `{"msg_en": "Torrent IDs do not belong to this bangumi", "msg_zh": "...", "mismatched_ids": [...]}`
3. 查询 bangumi 获取保存路径等配置
4. 调用 `DownloadClient.add_torrent()` 批量添加到下载客户端
5. 添加完成后，通过 `torrents_info` 按 save_path/category 反查 qBittorrent 获取新种子的 hash
6. 更新 torrent 记录的 `downloaded=True` 和反查到的 `qb_hash`；如果反查失败则仅设 `downloaded=True`
7. 返回成功/失败结果

**关于 `downloaded` 语义**: 在 recollect 场景中，`downloaded=True` 表示"已提交给下载客户端"。实际的下载完成状态由 renamer 流程在重命名时处理。

### 新增/修改文件

- `backend/src/module/api/bangumi.py` — 新增两个端点
- `backend/src/module/models/torrent.py` — 新增 `TorrentDetail` 和 `RecollectRequest` 模型
- `backend/src/module/database/torrent.py` — 新增 `search_by_bangumi_id(bangumi_id)` 方法

## 数据流

```
用户点击「集数管理」
    → 前端打开弹框，调用 GET /bangumi/{id}/torrents
    → 后端查询 torrent 表 + qBittorrent 状态
    → 返回合并后的种子列表
    → 前端渲染表格，默认选中未下载项

用户点击「重新收集下载」
    → 前端发送 POST /bangumi/{id}/recollect { torrent_ids: [...] }
    → 后端从数据库取 torrent URL
    → 调用 DownloadClient.add_torrent() 添加到下载客户端
    → 更新数据库 downloaded/qb_hash
    → 返回结果
    → 前端显示 toast，关闭弹框
```

## 边界情况

1. **无种子记录**: 如果 bangumi_id 下没有任何 torrent，显示空状态引导
2. **下载客户端不可用**: 种子列表仍可展示，但状态降级为仅用数据库字段；重新收集时返回错误
3. **种子 URL 已失效**: 种子添加可能失败，API 返回失败信息，用户需要手动处理
4. **并发问题**: 多次点击重新收集时，按钮显示 loading 状态防止重复提交

## 不在范围内

- 主动搜索缺失集数（可通过后续迭代增加"搜索补全"按钮）
- 跨规则合并展示种子
- 二次确认弹框
- 种子详细信息的展开查看
