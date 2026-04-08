# 代码链路分析报告

## 概述
- 分析文件：`backend/src/module/rss/analyser.py`
- 分析时间：2026-04-07
- 语言类型：Python 3.10+ (async/await)

## 调用链路图

### 下游调用（analyser.py 调用的函数）

```
RSSAnalyser
├── 继承 TitleParser (module/parser/title_parser.py)
│   ├── .raw_parser(raw)           → raw_parser() 或 OpenAIParser.parse()
│   ├── .tmdb_parser(title, season, lang)  → tmdb_parser() (module/parser/analyser/tmdb_parser.py)
│   └── .mikan_parser(homepage)    → mikan_parser() (module/parser/analyser/)
│
├── .official_title_parser(bangumi, rss, torrent)
│   ├── self.mikan_parser(torrent.homepage)          [当 rss.parser == "mikan"]
│   ├── self.tmdb_parser(title, season, language)    [当 rss.parser == "tmdb"]
│   └── AIMatcher.search_and_match()                 [AI 增强搜索, 条件触发]
│       ├── AIMatcher._generate_keywords(title)      → OpenAI API (同步→线程)
│       ├── tmdb_search_fn(keyword)                  → tmdb_parser() (闭包)
│       └── AIMatcher._pick_best_match()             → OpenAI API (同步→线程)
│
├── .get_rss_torrents(rss_link, full_parse)
│   └── RequestContent.get_torrents(rss_link, filter)
│
├── .torrents_to_data(torrents, rss, full_parse)
│   ├── self.raw_parser(torrent.name)
│   └── self.official_title_parser(bangumi, rss, torrent)
│
├── .torrent_to_data(torrent, rss)
│   ├── self.raw_parser(torrent.name)
│   └── self.official_title_parser(bangumi, rss, torrent)
│
├── .rss_to_data(rss, engine, full_parse)
│   ├── self.get_rss_torrents(rss.url, full_parse)
│   ├── engine.bangumi.match_list(rss_torrents, rss.url)
│   ├── self.torrents_to_data(torrents_to_add, rss, full_parse)
│   ├── engine.bangumi.add_all(new_data)
│   └── self._fetch_dandanplay_titles(new_data)      [fire-and-forget]
│
├── ._fetch_dandanplay_titles(bangumi_list)
│   └── asyncio.create_task(_do_fetch())
│       └── batch_update_dandanplay_titles(records, app_id, app_secret)
│           └── DandanplayClient.search(official_title) → HTTP GET api.dandanplay.net
│
└── .link_to_data(rss)
    ├── self.get_rss_torrents(rss.url, False)
    └── self.torrent_to_data(torrent, rss)
```

### 上游调用（谁调用了 RSSAnalyser）

```
RSSThread.rss_loop()                    [module/core/sub_thread.py:34]
└── analyser.rss_to_data(rss, engine)

API /api/v1/rss/analysis                [module/api/rss.py:180]
└── analyser.link_to_data(rss)

MCP Tools add_bangumi()                 [module/mcp/tools.py:269]
└── analyser.link_to_data(rss)

SearchTorrent (多重继承)                [module/searcher/searcher.py:29]
└── self.torrent_to_data(torrent, rss_item)  [analyse_keyword 方法内]
```

## 数据链路图

### 核心数据流：RSS 种子 → Bangumi 数据库记录

```
[外部 RSS Feed]
       │
       ▼
get_rss_torrents(rss.url)  ──→  RequestContent.get_torrents()
       │                          │ HTTP GET
       ▼                          ▼
list[Torrent]               list[Torrent]  (name, homepage, rss_id, ...)
       │
       ▼
engine.bangumi.match_list(torrents, rss_url)
       │  用 title_raw + aliases 正则匹配已有 Bangumi
       │  过滤掉已匹配的种子
       ▼
list[Torrent]  (仅新增的、未匹配的种子)
       │
       ▼
torrents_to_data() / torrent_to_data()
       │
       ├─► raw_parser(torrent.name)
       │       │  正则/规则解析 或 OpenAI 解析
       │       ▼
       │   Bangumi(
       │       official_title = title_raw (初始),
       │       title_raw, season, group_name, dpi, ...
       │   )
       │
       ├─► official_title_parser(bangumi, rss, torrent)
       │       │
       │       ├─ [mikan] mikan_parser(homepage)
       │       │       → 更新 official_title, poster_link
       │       │       → tmdb_matched = True
       │       │
       │       ├─ [tmdb]  tmdb_parser(title, season, lang)
       │       │       → 更新 official_title, year, season, poster_link
       │       │       → tmdb_matched = True  (当 year 或 poster_link 非 None)
       │       │
       │       └─ [AI fallback]  AIMatcher.search_and_match()
       │               → 更新 official_title (confidence >= 0.7)
       │
       ▼
Bangumi (完整元数据)
       │
       ├─► engine.bangumi.add_all(new_data)  → 写入 SQLite
       │
       └─► _fetch_dandanplay_titles(new_data)  → fire-and-forget 异步
               │
               └─► batch_update_dandanplay_titles()
                       │
                       ├─► DandanplayClient.search(official_title)
                       │       HTTP GET api.dandanplay.net/api/v2/search/anime
                       │       → 返回 animeTitle
                       │
                       └─► db.bangumi.update_dandanplay_title(id, title)
                               → 写入 bangumi.dandanplay_title 列
```

## 链路详情

### 1. tmdb_matched 标志逻辑（official_title_parser, L16-86）

| 步骤 | rss.parser 值 | 执行逻辑 | tmdb_matched 结果 |
|------|--------------|---------|-------------------|
| Mikan | `"mikan"` | 调用 `mikan_parser(torrent.homepage)`，成功后设为 `True` | `True` (成功) / `False` (AttributeError) |
| TMDB | `"tmdb"` | 调用 `tmdb_parser()`，检查 `year is not None or poster_link is not None` | `True` (有结果) / `False` (均 None) |
| 其他 | 其他字符串 | `else: pass`，不执行任何操作 | `False` |

**关键判断**：AI 增强搜索的触发条件为 `settings.experimental_openai.enable and not tmdb_matched`。

### 2. AI 增强搜索触发条件（L42-86）

触发条件链：
1. `settings.experimental_openai.enable == True`
2. `tmdb_matched == False`（Mikan/TMDB 均未成功匹配）

执行流程：
1. 延迟导入 `AIMatcher`，创建实例
2. 定义 `tmdb_search_fn` 闭包：调用 `tmdb_parser(keyword, language)` 并格式化为 `list[dict]`
3. 定义 `tmdb_formatter` 闭包：将候选列表格式化为文本
4. 调用 `matcher.search_and_match()`：
   - LLM 生成 3-5 个搜索关键词
   - 对每个关键词调用 `tmdb_search_fn`（每个间隔 0.25s）
   - 按 TMDB ID 去重
   - LLM 从候选中选最佳匹配
5. 置信度 >= 0.7 时更新 `official_title`

### 3. rss_to_data 中的 dandanplay 触发（L123-140）

触发时机：`rss_to_data` 方法中，`engine.bangumi.add_all(new_data)` 之后。

前置条件（在 `_fetch_dandanplay_titles` 内检查）：
1. `settings.bangumi_manage.rename_method` 为 `"dandanplay"` 或 `"subtitle_dandanplay"`
2. `settings.dandanplay.enable == True`

### 4. _fetch_dandanplay_titles 的异步处理（L142-165）

这是一个 `@staticmethod` 方法，内部通过 `asyncio.create_task()` 创建后台任务。

**执行模式**：fire-and-forget，不等待结果，不处理成功/失败（仅 debug 日志）。

**潜在问题**：参见下方问题清单。

## 问题清单

### 严重问题（8-10分）

#### P1: asyncio.create_task() 可能导致 "no running event loop" 或任务静默丢失（评分：9）

**位置**：`_fetch_dandanplay_titles` L163

**描述**：`_fetch_dandanplay_titles` 是 `@staticmethod`，内部调用 `asyncio.create_task(_do_fetch())`。如果调用方在非 asyncio 上下文中执行（例如同步代码路径），`asyncio.create_task()` 会抛出 `RuntimeError: no running event loop`。虽然当前上游调用者 `rss_to_data` 是 async 方法，且由 `RSSThread.rss_loop` 中的 asyncio task 驱动，但 `asyncio.create_task` 将任务绑定到当前运行的事件循环。如果事件循环在任务完成前关闭（例如程序退出），任务会被静默取消，不会有任何日志。

**影响**：dandanplay 标题获取可能在程序关闭时静默丢失，无告警。

**建议**：
- 方案 A：将 `_do_fetch` 改为直接 `await`，让 `rss_to_data` 显式等待完成（但会增加 RSS 处理延迟）。
- 方案 B：保持 fire-and-forget，但在 `RSSThread` 关闭时通过 `asyncio.TaskGroup` 或 `asyncio.gather` 等待所有挂起的 dandanplay 任务。
- 方案 C：将 task 引用保存到类实例或全局变量，在关闭时检查和清理。

#### P2: batch_update_dandanplay_titles 内部逐条创建 Database session，无事务保护（评分：8）

**位置**：`module/searcher/dandanplay.py` L77-106

**描述**：`batch_update_dandanplay_titles` 在 for 循环中为每条记录创建独立的 `Database()` 上下文管理器。这意味着：
1. 每条记录独立 commit，如果中途失败，已更新的记录不会回滚，造成数据不一致。
2. 在 `rss_to_data` 中刚 `add_all(new_data)` 写入的记录，紧接着在另一个 session 中被读取和更新。由于 SQLite 的隔离级别，可能出现 session 间数据不可见的情况（虽然 `Database()` 上下文管理器通常会创建新 session）。

**影响**：批量更新时部分成功部分失败，数据状态不一致。

### 一般问题（5-7分）

#### P3: tmdb_matched 标志语义不准确（评分：7）

**位置**：`official_title_parser` L23

**描述**：当 `rss.parser == "mikan"` 时，`mikan_parser` 成功返回后直接设置 `tmdb_matched = True`。但 `tmdb_matched` 这个变量名暗示的是 "TMDB 匹配成功"，而 Mikan parser 成功并不等于 TMDB 匹配成功。这导致：
1. 如果用户配置了 `parser = "mikan"` 且 Mikan 成功，AI 增强搜索永远不会触发，即使 Mikan 返回的标题质量很差。
2. 变量名 `tmdb_matched` 的语义与实际含义（"标题增强已成功"）不符，增加了维护成本。

**建议**：将变量名改为 `title_enhanced` 或 `official_title_resolved`，使其语义与实际用途一致。

#### P4: Mikan parser 的异常处理过于宽泛（评分：6）

**位置**：`official_title_parser` L18-26

**描述**：`mikan_parser` 的失败仅捕获 `AttributeError`，注释说明是 "Mikan torrent has no homepage info"。但如果 `torrent.homepage` 是 `None` 或空字符串，`mikan_parser` 内部可能会抛出 `TypeError` 或返回无效结果，这些情况不会被捕获。另外，`mikan_parser` 如果返回 `(None, None)` 元组，`bangumi.poster_link` 和 `bangumi.official_title` 会被设为 `None`，但 `tmdb_matched` 仍为 `True`，阻止了后续 AI 增强搜索。

**建议**：
- 检查 `mikan_parser` 返回值的有效性（如 `homepage` 是否为 None/空）。
- 在设置 `tmdb_matched = True` 前验证返回的 `official_title` 非空。

#### P5: _fetch_dandanplay_titles 的 settings 检查是冗余的双重检查（评分：5）

**位置**：`_fetch_dandanplay_titles` L146-151 vs `rss_to_data` L137

**描述**：`rss_to_data` 在调用 `_fetch_dandanplay_titles` 之前不做任何条件检查，而 `_fetch_dandanplay_titles` 内部检查了 `rename_method` 和 `dandanplay.enable`。这意味着即使不需要 dandanplay 标题，每次 `rss_to_data` 都会进入 `_fetch_dandanplay_titles` 方法（虽然会立即 return）。这不是性能问题，但调用语义不清晰。

**建议**：在 `rss_to_data` 中提前检查条件，避免不必要的函数调用。

### 轻微问题（1-4分）

#### P6: RSSAnalyser 在 API 模块中作为模块级单例实例化（评分：4）

**位置**：`module/api/rss.py` L173: `analyser = RSSAnalyser()`

**描述**：`RSSAnalyser` 在 API 模块加载时创建单例，同时 `RSSThread` 中也创建了一个实例（`sub_thread.py` L24）。`RSSAnalyser` 本身是无状态的（继承自无状态的 `TitleParser`），所以不会有数据竞争问题。但 `SearchTorrent` 通过多重继承继承了 `RSSAnalyser` 的方法，这种设计模式使得方法归属不清晰。

#### P7: AI 增强搜索中 tmdb_search_fn 闭包重复导入模块（评分：3）

**位置**：`official_title_parser` L50

**描述**：每次调用 `official_title_parser` 时，如果进入 AI 增强搜索分支，都会执行 `from module.parser.analyser.tmdb_parser import tmdb_parser`。虽然 Python 的 import 系统有缓存不会重复加载，但在热路径上使用延迟导入的模式不太常见。同样，`from module.searcher.ai_matcher import AIMatcher` (L43) 也是延迟导入。

**建议**：可以将这些导入移到文件顶部。延迟导入通常用于避免循环依赖，这里不太存在该问题。

#### P8: raw_parser 中 OpenAI 路径缺少 None 检查（评分：2）

**位置**：`title_parser.py` L64-68（被 RSSAnalyser 继承）

**描述**：当 `settings.experimental_openai.enable` 为 True 时，`OpenAIParser.parse(raw, asdict=True)` 返回的 `episode_dict` 直接用于构造 `Episode(**episode_dict)`。如果 OpenAI 返回的 JSON 缺少必要字段，会抛出 `TypeError`。虽然外层有 `except (ValueError, AttributeError, TypeError)`，但 `TypeError` 的错误信息不够具体，不利于调试。

## 建议

### 优先级排序

1. **[P1] 修复 asyncio.create_task 生命周期管理**：在 `RSSThread.rss_stop` 中确保 dandanplay 后台任务完成后再退出，或改用显式 await 模式。
2. **[P2] 为 batch_update_dandanplay_titles 添加事务保护**：使用单个 Database session 包裹整个批量操作，失败时回滚。
3. **[P3] 重命名 tmdb_matched 为 title_enhanced**：使变量语义与实际用途一致，减少维护困惑。
4. **[P4] 加强 Mikan parser 返回值验证**：在设置 `tmdb_matched = True` 前检查 `official_title` 非空。

### 架构观察

当前 `RSSAnalyser` 承担了三个职责：
- RSS 种子获取和解析（`get_rss_torrents`, `rss_to_data`）
- 标题增强/解析（`official_title_parser`）
- Dandanplay 集成（`_fetch_dandanplay_titles`）

随着 AI 搜索和 Dandanplay 的引入，这个类的职责边界在扩大。如果后续继续添加新的标题增强策略，建议将 `official_title_parser` 中的增强逻辑抽为独立的策略链（Strategy Pattern），将 Dandanplay 集成移至独立的 manager 类。
