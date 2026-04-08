# 代码链路分析报告

## 概述
- 分析文件：`backend/src/module/manager/renamer.py`
- 分析时间：2026-04-07
- 语言类型：Python 3.10+
- 文件职责：负责已下载番剧文件的重命名，包括媒体文件和字幕文件。通过与 qBittorrent API 交互完成实际重命名操作，支持多种命名策略（pn/advance/dandanplay 等）和集数/季度偏移量。

## 调用链路图

### 上游调用链（谁调用了 Renamer）

```
RenameThread.rename_loop()          [module/core/sub_thread.py:70]
  └─ async with Renamer() as renamer  [sub_thread.py:73]  (DownloadClient.__aenter__ 触发 auth)
       └─ renamer.rename()            [sub_thread.py:74]
            ├─ self.get_torrent_info()       → DownloadClient.get_torrent_info()
            ├─ self.get_torrent_files(hash)  → DownloadClient.get_torrent_files()
            ├─ self._batch_lookup_offsets()  → Database 查询
            ├─ self.check_files(files)       → TorrentPath.check_files()
            ├─ self._path_to_bangumi()       → TorrentPath._path_to_bangumi()
            ├─ self.rename_file()            → TitleParser.torrent_parser() + gen_path()
            ├─ self.rename_collection()      → TitleParser.torrent_parser() + gen_path()
            ├─ self.rename_subtitles()       → TitleParser.torrent_parser() + gen_path()
            └─ self.set_category()           → DownloadClient.set_category()
```

### 继承链

```
Renamer(DownloadClient)
  └─ DownloadClient(TorrentPath)
       └─ TorrentPath  [module/downloader/path.py]
```

### 下游调用链（Renamer 调用了什么）

```
Renamer
  ├─ gen_path()                          [静态方法，路径生成]
  ├─ rename_file()                       [单文件重命名]
  │    ├─ TitleParser.torrent_parser()   [module/parser/title_parser.py:22]
  │    │    └─ torrent_parser()          [module/parser/analyser/torrent_parser.py:73]
  │    ├─ gen_path()                     [生成新路径]
  │    └─ rename_torrent_file()          [DownloadClient → qBittorrent API]
  ├─ rename_collection()                 [多文件重命名]
  │    ├─ is_ep()                        [TorrentPath 方法]
  │    ├─ TitleParser.torrent_parser()
  │    ├─ gen_path()
  │    └─ rename_torrent_file()
  ├─ rename_subtitles()                  [字幕重命名]
  │    ├─ TitleParser.torrent_parser(file_type="subtitle")
  │    ├─ gen_path(method="subtitle_" + method)
  │    └─ rename_torrent_file(verify=False)
  ├─ _batch_lookup_offsets()             [批量偏移量查询]
  │    ├─ Database()                     [数据库会话]
  │    ├─ db.torrent.search_by_qb_hashes()
  │    ├─ db.bangumi.search_ids()
  │    ├─ db.bangumi.match_torrent()
  │    ├─ db.bangumi.match_by_save_path()
  │    └─ _parse_bangumi_id_from_tags()
  └─ _lookup_offsets()                   [单条偏移量查询，当前未被 rename() 调用]
```

## 数据链路图

### RenameInfo 数据流（核心数据流）

```
Bangumi 表 (SQLite)
  ├─ episode_offset: int
  ├─ season_offset: int
  └─ dandanplay_title: Optional[str]
       ↑
       │ (由 batch_update_dandanplay_titles 写入)
       │
  searcher/dandanplay.py
    DandanplayClient.search(official_title)
      → api.dandanplay.net/api/v2/search/anime
      → 返回 animes[0].animeTitle
       ↓
_batch_lookup_offsets()  [renamer.py:283]
  4 层查找优先级:
  1. qb_hash → torrent.bangumi_id → bangumi
  2. tag "ab:ID" → bangumi_id → bangumi
  3. torrent_name → match_torrent()
  4. save_path → match_by_save_path()
       ↓
  RenameInfo(episode_offset, season_offset, dandanplay_title)
       ↓
  offset_map: dict[str, RenameInfo]
       ↓
rename() [renamer.py:459]
  rename_info = offset_map.get(torrent_hash, RenameInfo(0, 0, None))
  episode_offset = rename_info.episode_offset
  season_offset = rename_info.season_offset
       ↓
  ┌─ if rename_method in ("dandanplay", "subtitle_dandanplay") and rename_info.dandanplay_title:
  │    bangumi_name = rename_info.dandanplay_title   ← 关键替换点
  │    (否则 bangumi_name 保持从 _path_to_bangumi() 获取的值)
  └─ kwargs 传入 rename_file / rename_collection / rename_subtitles
       ↓
gen_path(bangumi_name, method, episode_offset, season_offset)
  → dandanplay 分支: f"{bangumi_name} S{season}E{episode}{suffix}"
```

### dandanplay_title 完整生命周期

```
1. 写入时机:
   RSS analyser 分析新番时  [rss/analyser.py:137]
     → _fetch_dandanplay_titles()
     → batch_update_dandanplay_titles()
     → db.bangumi.update_dandanplay_title(id, title)

   后台定时任务 (sub_thread.py:236)
     → batch_update_dandanplay_titles()

   API 手动触发  [api/config.py:65]
     → batch_update_dandanplay_titles()

2. 存储位置:
   Bangumi 表 dandanplay_title 列 (TEXT, nullable)
   迁移: combine.py:117 ALTER TABLE bangumi ADD COLUMN dandanplay_title

3. 读取使用:
   _batch_lookup_offsets() 从 Bangumi 对象提取 b.dandanplay_title
   → 封装进 RenameInfo.dandanplay_title
   → rename() 中当 method 为 dandanplay 时替换 bangumi_name
   → gen_path() 生成最终文件路径
```

### gen_path 分支逻辑

```
gen_path(file_info, bangumi_name, method, episode_offset, season_offset)
  │
  ├─ "none" / "subtitle_none"     → 返回原路径 (不重命名)
  ├─ "pn"                          → "{title} S{S}E{E}{suffix}"
  ├─ "advance"                     → "{bangumi_name} S{S}E{E}{suffix}"
  ├─ "normal"                      → 返回原路径 (已废弃)
  ├─ "subtitle_pn"                 → "{title} S{S}E{E}.{lang}{suffix}"
  ├─ "subtitle_advance"            → "{bangumi_name} S{S}E{E}.{lang}{suffix}"
  ├─ "dandanplay"                  → "{bangumi_name} S{S}E{E}{suffix}"
  │                                   ↑ 与 advance 输出格式完全相同
  │                                   ↑ 差异在调用方: bangumi_name 被 dandanplay_title 替换
  ├─ "subtitle_dandanplay"         → "{bangumi_name} S{S}E{E}.{lang}{suffix}"
  │                                   ↑ 与 subtitle_advance 输出格式完全相同
  └─ 未知 method                   → 返回原路径 + error 日志
```

### 与 downloader 层 rename_torrent_file 的交互

```
Renamer.rename_file()
  └─ await self.rename_torrent_file(_hash, old_path, new_path)    [renamer.py:148]
       │
       ↓ (self 是 DownloadClient 实例)
DownloadClient.rename_torrent_file()  [download_client.py:135]
  └─ await self.client.torrents_rename_file(hash, old, new, verify=True)
       │
       ↓ (self.client 是 QbDownloader/Aria2Downloader/MockDownloader)
QbDownloader.torrents_rename_file()
  → POST /api/v2/torrents/renameFile
  → {hash, oldPath, newPath}
       │
       ↓
返回 bool
  ├─ True:  从 _pending_renames 移除，返回 Notification
  └─ False: 加入 _pending_renames 缓存 (cooldown 5 分钟)
```

### pending renames 防抖机制

```
模块级缓存: _pending_renames: dict[(hash, old, new), timestamp]

rename_file() 中:
  1. 检查 pending_key 是否在缓存中
  2. 若存在且未超过 300s 冷却期 → 跳过重命名
  3. 调用 rename_torrent_file()
  4. 成功 → 从缓存移除
  5. 失败 → 加入缓存，触发 _cleanup_pending_cache()

_cleanup_pending_cache():
  节流: 最多每 60s 清理一次
  清理条件: 缓存时间 > 600s (2 倍冷却期)
```

## 链路详情

| 函数 | 输入 | 输出 | 关键依赖 |
|------|------|------|---------|
| `rename()` | 无 (从 settings/downloader 获取) | `list[Notification]` | settings, DownloadClient, Database |
| `_batch_lookup_offsets()` | `list[dict]` (torrents_info) | `dict[str, RenameInfo]` | Database (torrent + bangumi) |
| `_lookup_offsets()` | hash, name, path, tags | `tuple[int, int]` | Database (未被 rename 调用) |
| `gen_path()` | file_info, bangumi_name, method, offsets | `str` (新路径) | 无外部依赖 |
| `rename_file()` | media_path + kwargs | `Optional[Notification]` | TitleParser, DownloadClient |
| `rename_collection()` | media_list + kwargs | `None` | TitleParser, DownloadClient |
| `rename_subtitles()` | subtitle_list + kwargs | `None` | TitleParser, DownloadClient |
| `_parse_bangumi_id_from_tags()` | tags: str | `Optional[int]` | 无 |
| `_normalize_path()` | path: str | `str` | 无 |
| `_cleanup_pending_cache()` | 无 | `None` | 模块级变量 |

## 问题清单

### 严重问题（8-10分）

**[P9] `_lookup_offsets()` 方法成为死代码**

`_lookup_offsets()` 方法（第 382-457 行）包含完整的四级查找逻辑，但 `rename()` 方法（第 459 行）已经切换为使用 `_batch_lookup_offsets()`。搜索整个代码库，`_lookup_offsets` 没有被任何其他代码调用。

- 影响：约 75 行死代码增加维护负担，且该方法不返回 `dandanplay_title`，与当前 `RenameInfo` 结构不一致，如果有人误用会产生 bug。
- 位置：`renamer.py:382-457`

### 一般问题（5-7分）

**[P6] dandanplay 和 advance 的 gen_path 分支逻辑完全重复**

`gen_path()` 中 `method == "dandanplay"` （第 101-102 行）与 `method == "advance"` （第 92-93 行）的返回值格式完全相同，`subtitle_dandanplay` 与 `subtitle_advance` 同理。

- 影响：两个分支的存在容易误导开发者认为它们有不同行为。实际的差异完全在调用方 `rename()` 中（第 482-483 行的 bangumi_name 替换），而非在 gen_path 内部。
- 建议：合并分支或在注释中明确说明差异仅在调用方的 bangumi_name 来源。

**[P6] `season_offset` 参数传递但未生效**

`gen_path()` 接收 `season_offset` 参数（第 65 行），但函数体中完全没有使用它。注释说明 "Kept for API compatibility, but no longer used"。然而 `rename_file()`、`rename_collection()`、`rename_subtitles()` 和 `rename()` 中都仍在传递此参数。

- 影响：如果其他代码依赖 season_offset 来影响文件名，当前不会生效。虽然 season_offset 已经通过文件夹名（`_gen_save_path` 中的 `Season {season + season_offset}`）实现了偏移，但函数签名仍然具有误导性。

**[P5] `_batch_lookup_offsets` 异常处理过于宽泛**

第 373 行 `except Exception as e` 捕获所有异常后静默回退到 `RenameInfo(0, 0, None)`。这会掩盖数据库连接失败、SQL 语法错误等需要立即关注的严重问题。

- 影响：数据库故障时所有 torrent 的偏移量被静默重置为 0，可能导致文件被错误重命名，且不会触发告警。

### 轻微问题（1-4分）

**[P4] `gen_path` 中 episode_offset 计算逻辑与 `rename_file` 重复**

`gen_path()` 第 74-86 行和 `rename_file()` 第 156-163 行有完全相同的 episode offset 调整逻辑（EP0 不偏移、负值回退）。两处独立维护容易产生不一致。

- 建议：将偏移计算提取为私有方法 `_apply_episode_offset(original_episode, offset) -> int`。

**[P3] `rename_collection` 缺少 pending renames 防抖**

`rename_file()` 有完整的 `_pending_renames` 防抖机制（第 136-174 行），但 `rename_collection()`（第 181-215 行）和 `rename_subtitles()`（第 217-254 行）没有使用此机制。

- 影响：多文件集合的重命名失败时会产生重复请求。

**[P2] `rename_subtitles` 的 verify=False 缺少重试机制**

字幕重命名时跳过验证（`verify=False`），但失败时仅打印 warning，不像 `rename_file` 那样有 pending cache。

**[P2] `dandanplay_title` 为 None 时 dandanplay 方法退化为 advance**

第 482 行检查 `rename_info.dandanplay_title` 是否为 truthy。当 dandanplay_title 为 None（API 未匹配或未配置 app_id/app_secret），`bangumi_name` 保持从 `_path_to_bangumi()` 获取的文件夹路径名，最终行为与 advance 方法一致。这是合理的 fallback，但用户可能不知道 dandanplay 方法未生效。

## 建议

1. **移除 `_lookup_offsets()` 死代码**（第 382-457 行）。该方法不被任何调用方使用，且缺少 `dandanplay_title` 返回值，保留会造成维护混乱。

2. **合并 dandanplay 和 advance 的 gen_path 分支**。在 gen_path 内部不需要区分 dandanplay 和 advance，它们的行为完全一致。可以在 gen_path 内部用 `"advance"` 处理两者，并在注释中说明 dandanplay 的差异在于调用方传入的 bangumi_name 来源。

3. **清理 `season_offset` 参数**。从 `gen_path`、`rename_file`、`rename_collection`、`rename_subtitles` 的签名中移除 `season_offset` 参数，因为实际偏移已通过文件夹名实现。如果需要保留 API 兼容性，使用 `**kwargs` 吞掉它。

4. **收紧异常处理**。`_batch_lookup_offsets` 的 except 应区分可恢复错误（如单条记录查询失败）和不可恢复错误（如数据库连接失败），后者应抛出异常或返回错误标记。

5. **提取 episode offset 计算为公共方法**。消除 `gen_path` 和 `rename_file` 之间的重复逻辑。
