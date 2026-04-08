# 代码链路分析报告

## 概述
- 分析文件：`backend/src/module/core/sub_thread.py`
- 分析时间：2026-04-07
- 语言类型：Python (asyncio)
- 文件职责：定义后台周期任务的 Thread 类，通过多重继承被 `Program` 组合使用

## 调用链路图

### 上游调用链

```
Program.start()                          [module/core/program.py:87]
  ├── RSSThread.rss_start()              [sub_thread.py:49]  (受 enable_rss 控制)
  ├── RenameThread.rename_start()        [sub_thread.py:89]  (受 enable_renamer 控制)
  ├── OffsetScanThread.scan_start()      [sub_thread.py:138] (无条件启动)
  ├── CalendarRefreshThread.calendar_start() [sub_thread.py:190] (无条件启动)
  └── DandanplayThread.dandanplay_start()    [sub_thread.py:260] (无条件启动)

Program.stop()                           [module/core/program.py:124]
  ├── rename_stop() -> RenameThread.rename_stop()
  ├── rss_stop()    -> RSSThread.rss_stop()
  ├── scan_stop()   -> OffsetScanThread.scan_stop()
  ├── calendar_stop() -> CalendarRefreshThread.calendar_stop()
  └── dandanplay_stop() -> DandanplayThread.dandanplay_stop()
```

### 继承关系

```
Checker (module/checker/checker.py)
  └── ProgramStatus (module/core/status.py)
        ├── RSSThread
        ├── RenameThread
        ├── OffsetScanThread
        ├── CalendarRefreshThread
        └── DandanplayThread
              └── Program (多重继承组合)
```

### DandanplayThread 下游调用链

```
DandanplayThread.dandanplay_loop()           [sub_thread.py:219]
  ├── settings.bangumi_manage.rename_method  [module/conf/config.py -> BangumiManage]
  ├── settings.dandanplay.enable             [module/conf/config.py -> DandanplayConfig]
  ├── Database()                             [module/database/combine.py:124]
  │     └── BangumiDatabase.get_bangumi_missing_dandanplay()  [module/database/bangumi.py:707]
  │           └── SELECT Bangumi WHERE dandanplay_title IS NULL
  │               AND dandanplay_retry_count < 3 AND deleted = false
  └── batch_update_dandanplay_titles()       [module/searcher/dandanplay.py:77]
        ├── DandanplayClient(app_id, app_secret)  [dandanplay.py:23]
        ├── for record in records:
        │     ├── DandanplayClient.search(official_title)  [dandanplay.py:38]
        │     │     ├── generate_signature()  [dandanplay.py:14]
        │     │     └── httpx.AsyncClient.get("https://api.dandanplay.net/api/v2/search/anime")
        │     ├── Database() -> BangumiDatabase.update_dandanplay_title()  [bangumi.py:695]
        │     │     ├── 成功: 设置 dandanplay_title, 重置 retry_count=0
        │     │     └── 失败: 设置 dandanplay_title=None, retry_count+=1
        │     └── except: Database() -> update_dandanplay_title(id, None)
        └── (内部自管理 session，每次循环独立开关)
```

## 数据链路图

### 配置数据流

```
config.json / .env
  └── Settings.load() / Settings.init()
        └── settings (模块级单例)
              ├── settings.bangumi_manage.rename_method: str  (默认 "pn")
              └── settings.dandanplay
                    ├── enable: bool       (默认 False)
                    ├── app_id: str        (默认 "")
                    └── app_secret: str    (默认 "")
```

### 数据库数据流

```
bangumi 表
  ├── dandanplay_title: Optional[str]     -- 弹弹Play匹配的标题
  ├── dandanplay_retry_count: int          -- 连续失败重试计数器
  ├── official_title: str                  -- 官方中文名（作为搜索关键词）
  └── deleted: bool                        -- 软删除标记

查询链路:
  get_bangumi_missing_dandanplay()
    → 返回 dandanplay_title IS NULL AND retry_count < 3 AND deleted = false 的 Bangumi 列表
    → 这些是 ORM 对象，绑定在外层 with Database() as db 的 session 上

写入链路:
  batch_update_dandanplay_titles() 内部独立开 Database() session
    → update_dandanplay_title(id, title)
      → search_id(id) 获取 bangumi 对象
      → 修改字段并 commit
      → 调用 _invalidate_bangumi_cache()
```

### 条件守卫数据流

```
dandanplay_loop() 每次循环迭代:
  1. 检查 rename_method ∈ {"dandanplay", "subtitle_dandanplay"}  -- 功能开关
  2. 检查 dandanplay.enable = True                               -- API 配置开关
  3. 两者均满足 → 执行查询和更新
  4. 任一不满足 → 跳过本轮，等待下一轮 24h 间隔
```

## 链路详情

### Thread 实现模式一致性对比

| 特征 | RSSThread | RenameThread | OffsetScanThread | CalendarRefreshThread | DandanplayThread |
|------|-----------|-------------|-----------------|---------------------|-----------------|
| 继承 ProgramStatus | Y | Y | Y | Y | Y |
| _xxx_task 字段 | Y | Y | Y | Y | Y |
| _xxx_stop_event | Y | Y | Y | Y | Y |
| xxx_loop() | Y | Y | Y | Y | Y |
| xxx_start() | Y | Y | Y | Y | Y |
| xxx_stop() | Y | Y | Y | Y | Y |
| while + stop_event 守卫 | Y | Y | Y | Y | Y |
| wait_for + timeout | Y | Y | Y | Y | Y |
| 初始 delay | N | N | 60s | 120s | 120s |
| 条件守卫 | N | N | N | N | Y (rename_method + enable) |
| 延迟导入 | N | N | N | N | Y (Database, dandanplay) |

### Database Session 管理对比

| Thread | Session 管理方式 | Session 作用域 |
|--------|----------------|---------------|
| RSSThread | `async with DownloadClient()` + `with RSSEngine()` | 每轮循环 |
| RenameThread | `async with Renamer()` | 每轮循环 |
| OffsetScanThread | 通过 self._scanner (OffsetScanner) 内部管理 | 每轮循环 |
| CalendarRefreshThread | `with TorrentManager()` | 每轮循环 |
| **DandanplayThread** | **外层 `with Database() as db` 查询 + `batch_update_dandanplay_titles` 内部独立 `with Database()` 写入** | **双层嵌套** |

### 启动控制对比

| Thread | 启动条件 | Program.start() 中的调用 |
|--------|---------|----------------------|
| RSSThread | `enable_rss` (rss_parser.enable) | 条件启动 |
| RenameThread | `enable_renamer` (bangumi_manage.enable) | 条件启动 |
| OffsetScanThread | 无条件 | 始终启动 |
| CalendarRefreshThread | 无条件 | 始终启动 |
| DandanplayThread | 无条件（内部有条件守卫） | 始终启动 |

## 问题清单

### 严重问题（8-10分）

#### P1: DetachedInstanceError 风险 -- 外层 session 关闭后 ORM 对象传入 async 函数

**位置**: `sub_thread.py:232-243`

**描述**: `with Database() as db:` 块中查询得到 `records`（SQLAlchemy ORM 对象），这些对象绑定在 `db` session 上。当 `with` 块结束时，session 关闭，对象变为 detached 状态。随后 `records` 被传入 `await batch_update_dandanplay_titles(records=records, ...)`。虽然 `batch_update_dandanplay_titles` 内部通过 `hasattr(record, "id")` 和 `hasattr(record, "official_title")` 访问属性（对 detached 对象的简单属性访问通常可行），但这依赖于 SQLAlchemy 的实现细节（expired/deferred loading 行为），属于脆弱设计。

**评分**: 7/10（实际触发概率中等，但设计上不够健壮）

**对比**: `batch_update_dandanplay_titles` 内部为每个 record 单独开 `with Database() as db` 做写入，说明设计者意识到了 session 隔离的需求，但外层查询的 session 没有做同样处理。

**建议**: 在 `with Database() as db` 块内，将 ORM 对象转换为 dict 或只提取必要字段（id, official_title）再传出。或者将 `batch_update_dandanplay_titles` 改为接收 `(id, official_title)` 元组列表。

---

#### P2: 条件守卫导致功能静默失效 -- 无条件启动但内部跳过

**位置**: `sub_thread.py:225-228`

**描述**: `DandanplayThread` 在 `Program.start()` 中无条件启动（第114行），但 `dandanplay_loop()` 内部有条件守卫（rename_method + dandanplay.enable）。当条件不满足时，线程空转 24 小时等待下一轮。这本身不是 bug，但与 `RSSThread`/`RenameThread` 的设计模式不一致 -- 后者在启动前就通过 `enable_rss`/`enable_renamer` 判断是否启动。

**影响**: 用户在日志中看到 `[DandanplayThread] Started dandanplay title refresh (every 24h)`，但实际什么也不做，可能造成困惑。

**评分**: 5/10

**建议**: 两种改进方案：
1. 在 `Program.start()` 中增加条件判断，与 RSS/Rename 一致
2. 在 `dandanplay_start()` 的日志中明确说明是否满足条件

### 一般问题（5-7分）

#### P3: 每条 record 单独开 Database session -- N+1 session 问题

**位置**: `module/searcher/dandanplay.py:84-106`

**描述**: `batch_update_dandanplay_titles` 对每条 record 都独立执行 `with Database() as db`，意味着每条记录都创建一个新的 SQLAlchemy Session + Connection。如果 `get_bangumi_missing_dandanplay()` 返回 N 条记录，则创建 N 个 session。

**评分**: 5/10（对于 24 小时执行一次的后台任务，性能影响有限，但设计上不够优雅）

**建议**: 在函数开头开一个 `with Database() as db`，所有写入复用同一 session，最后统一 commit。

---

#### P4: 外层 Database session 仅用于查询，与内层写入 session 割裂

**位置**: `sub_thread.py:232` vs `dandanplay.py:93`

**描述**: `dandanplay_loop()` 外层 `with Database() as db` 仅调用 `get_bangumi_missing_dandanplay()` 做查询，而写入在 `batch_update_dandanplay_titles` 内部的独立 session 中完成。这导致：
- 查询和写入不在同一事务中，存在竞态条件（虽然 24h 间隔降低了概率）
- 外层 session 打开但仅用于一次 SELECT，显得多余

**评分**: 4/10

---

#### P5: DandanplayThread 启动不检查 dandanplay.enable 和 app_id/app_secret 有效性

**位置**: `program.py:114`, `sub_thread.py:260-263`

**描述**: 即使 `dandanplay.enable = False` 或 `app_id`/`app_secret` 为空字符串，`dandanplay_start()` 仍然会启动任务并打印 `[DandanplayThread] Started dandanplay title refresh (every 24h)`。虽然 `dandanplay_loop` 内部有条件检查会跳过执行，但空转浪费一个 asyncio Task。

**评分**: 4/10

### 轻微问题（1-4分）

#### P6: 延迟导入的风格不一致

**位置**: `sub_thread.py:230-237`

**描述**: `Database` 和 `batch_update_dandanplay_titles` 在函数内部延迟导入，其他 Thread 类的依赖都在文件顶部导入。延迟导入的目的是避免循环引用（`module.database` -> `module.models` 链路），但缺乏注释说明原因。

**评分**: 2/10

---

#### P7: 日志级别使用可以更精确

**位置**: `sub_thread.py:248`

**描述**: `No missing titles to update` 使用 `logger.debug`，考虑到这是 24 小时执行一次的定期任务，使用 `debug` 级别意味着默认配置下完全不可见。可以考虑用 `info` 以便运维确认线程正常工作。

**评分**: 1/10

## 建议

### 架构层面

1. **统一 Thread 启动模式**: `DandanplayThread` 的启动条件应与 `RSSThread`/`RenameThread` 对齐。建议在 `Program.start()` 中增加条件判断，或者在 `DandanplayThread` 中添加类似 `enable_dandanplay` 的属性。

2. **解耦 session 管理**: 将 `dandanplay_loop` 中的查询逻辑移入 `batch_update_dandanplay_titles` 内部，让该函数自行管理完整的查询-更新生命周期，消除外层 session 仅用于查询的割裂设计。

3. **消除 detached 对象传递**: 将 ORM 对象转换为简单数据结构（如 NamedTuple 或 dataclass）再跨 session 传递，避免依赖 SQLAlchemy 的 detached 行为。

### 代码层面

4. **为延迟导入添加注释**: 在 `from module.database import Database` 和 `from module.searcher.dandanplay import ...` 处添加注释，说明延迟导入的原因（避免循环依赖）。

5. **考虑 batch session**: `batch_update_dandanplay_titles` 可改为接收 `(id, official_title)` 列表，内部统一管理单个 session 完成所有写入。
