# AI 增强搜索与弹弹 Play 番名对齐

## 背景

RSS 订阅时，TMDB/Mikan 搜索经常因标题差异（缩写、罗马音、中/日/英文混用、简繁体等）搜不到对应番剧，导致无法创建 bangumi 记录。同时，下载后的文件重命名使用的番名（来自 TMDB/Mikan）与弹弹 Play 数据库中的番名不一致，导致 mpv + 弹弹 play 手动搜索弹幕时匹配失败。

## 目标

1. **AI 增强搜索**：TMDB/Mikan 搜索失败时，利用 LLM 生成多语言/多变体关键词重新搜索，提高 bangumi 创建成功率
2. **弹弹 Play 番名对齐**：将弹弹 Play 的番名保存到 bangumi 记录中，重命名时可选使用该番名，使文件名与弹弹 Play 弹幕库匹配

## 功能 A：AI 增强搜索

### 触发条件

在 `RSSAnalyser.official_title_parser()`（`analyser.py:15`）中，TMDB/Mikan 搜索完成后检测。具体条件：`bangumi.official_title == bangumi.title_raw`（说明 TMDB 未成功替换标题，仍使用 raw parser 提取的标题）。Mikan parser 失败（`AttributeError` 或无 homepage）时同样触发。

### 流程

```
种子标题 → raw_parser 解析 → 提取番名
  → TMDB/Mikan 搜索
    → 成功（返回有效 TMDBInfo 且 official_title != title_raw）：正常创建 bangumi
    → 失败：进入 AI 增强流程
      → LLM 生成关键词组（中文/日文/英文/罗马音/简繁体变体）
      → 串行用每个关键词搜索 TMDB（间隔 250ms，遵守 TMDB rate limit）
      → 去重所有搜索结果（以 TMDB ID 为去重键）
      → LLM 从候选中决策最佳匹配
        → 置信度 >= 0.7：用匹配结果创建 bangumi
        → 置信度 < 0.7 或无结果：放弃，记录日志
```

### 去重策略

以 TMDB ID 为去重键，避免同一番剧的多个搜索结果重复出现。

### 结果缓存

AI 生成的关键词和匹配结果不做持久化缓存。原因：同一种子通过 `check_new`（URL 去重）不会重复触发，每次 AI 增强搜索的场景都是不同的种子标题。

## 功能 B：弹弹 Play 番名对齐

### 数据模型

bangumi 表新增字段：

```sql
ALTER TABLE bangumi ADD COLUMN dandanplay_title TEXT DEFAULT NULL;
ALTER TABLE bangumi ADD COLUMN dandanplay_retry_count INTEGER DEFAULT 0;
```

`Bangumi` 和 `BangumiUpdate` 两个模型都需要添加 `dandanplay_title` 字段。`BangumiUpdate` 中标记为 `Optional[str]`，API 更新时如果未传递该字段则不覆盖。`dandanplay_retry_count` 仅在 `Bangumi` 模型中添加，不暴露到 API。

### 弹弹 Play API

使用弹弹 Play 搜索 API（`GET /api/v2/search/anime?keyword={keyword}`）获取番剧名称。API v2 需要认证，认证方式为请求头签名：`X-AppId`、`X-Timestamp`、`X-Signature`（`base64(sha256(AppId + Timestamp + Path + AppSecret))`）。

新增配置项，作为 `Config` 模型的独立顶层字段：

```python
class DandanplayConfig(BaseModel):
    enable: bool = False
    app_id: str = ""
    app_secret: str = ""
```

### 获取时机

**前置条件**：仅当 `rename_method == "dandanplay"` 且 `dandanplay.enable` 为 True 时才启用。

**首次选择时的全量补全**：用户首次将 rename_method 切换为 `dandanplay` 时，自动触发一次对 `dandanplay_title IS NULL` 的所有未删除 bangumi 记录的批量补全。

**创建时同步获取**：前置条件满足时，bangumi 创建成功后异步调用弹弹 Play API 搜索并写入 `dandanplay_title`。

**后台定期补全**：每 24 小时扫描一次 `dandanplay_title IS NULL` 的记录。对连续 3 次补全失败的记录跳过（避免对弹弹 Play 未收录的番剧无限重试），需要 `dandanplay_retry_count` 字段记录失败次数。

### AI 与非 AI 模式

- **AI 未开启**（`experimental_openai.enable == False`）：用 `official_title` 直接搜索弹弹 Play API，取第一个结果
- **AI 开启**：复用 AIMatcher，由 AI 生成关键词搜索弹弹 Play，再由 AI 决策最佳匹配

### 重命名变更

**数据流变更**：当前 renamer 的 `bangumi_name` 来自 `_path_to_bangumi(save_path)` 从文件夹名解析（`path.py:38-52`），不查数据库。新增 dandanplay rename method 需要在 renamer 的 `rename()` 方法中额外查询数据库获取对应 bangumi 的 `dandanplay_title`。

具体实现：`_batch_lookup_offsets` 返回类型从 `dict[str, tuple[int, int]]` 改为 `dict[str, RenameInfo]`，其中 `RenameInfo` 是一个 NamedTuple `(episode_offset, season_offset, dandanplay_title)`。在已有的 bangumi 批量查询中一并获取 `dandanplay_title`。`rename()` 中的解构代码相应适配。

新增 rename method：

- `dandanplay`：`{dandanplay_title} S{season}E{episode}.{suffix}`
- `subtitle_dandanplay`：`{dandanplay_title} S{season}E{episode}.{language}{suffix}`

当 `dandanplay_title` 为 `None` 或空字符串时，fallback 到 `official_title`（等同于 advance）。

**作用范围**：仅影响文件名，不影响文件夹名（文件夹名仍使用 TMDB/Mikan 的 `official_title`）。

## 通用模块：AIMatcher

### 职责

提供 AI 辅助搜索匹配的通用流程，功能 A 和功能 B 的 AI 模式共用。

### 接口

```python
class MatchResult:
    matched_item: Any    # 匹配到的搜索结果
    confidence: float    # 置信度 0-1

class AIMatcher:
    def __init__(self, openai_config: dict):
        ...

    async def search_and_match(
        self,
        title: str,                    # 原始标题
        search_fn: Callable,           # 搜索函数 (keyword) -> list[result]
        result_formatter: Callable,    # 格式化结果为 AI 可读文本
    ) -> Optional[MatchResult]:
        ...
```

### 异步适配

现有 `OpenAIParser` 使用 `ThreadPoolExecutor` 同步调用 OpenAI API。AIMatcher 的 `search_and_match` 是 async 方法，内部通过 `asyncio.to_thread` 包装 `OpenAIParser` 的同步调用，使其与 async 调用链兼容。

### LLM 响应格式

复用现有 `OpenAIParser` 的 `beta.chat.completions.parse`（结构化输出），为关键词生成和匹配决策分别定义 Pydantic response model，确保 LLM 返回符合预期的结构化数据。

### 流程

1. LLM 根据标题生成 3-5 个候选关键词（考虑中文/日文/英文/罗马音/简繁体变体）
2. 调用 `search_fn` 搜索每个关键词（串行，间隔 250ms）
3. 对所有搜索结果去重
4. 将去重后的候选列表格式化后发给 LLM，LLM 返回最佳匹配和置信度
5. 置信度低于阈值（0.7）时返回 None

### 配置

复用 `experimental_openai` 配置（base_url、api_key、model 等），共用同一个 LLM 连接。

## 开关设计

| 配置项 | 功能 A 影响 | 功能 B 影响 |
|--------|-----------|-----------|
| `experimental_openai.enable` | 控制是否启用 AI 增强 | 控制弹弹 Play 搜索是否走 AI 流程 |
| `rename_method == "dandanplay"` | 无影响 | 控制是否启用弹弹 Play 番名获取和重命名 |
| `dandanplay.enable` | 无影响 | 弹弹 Play API 认证配置（独立于 AI） |

三个条件的关系：功能 B 需要同时满足 `rename_method == "dandanplay"` 和 `dandanplay.enable` 才会触发。AI 开关仅决定搜索流程是否走 AI 路径。

## 新增文件

| 文件 | 用途 |
|------|------|
| `backend/src/module/searcher/ai_matcher.py` | 通用 AI 搜索匹配模块 |
| `backend/src/module/searcher/dandanplay.py` | 弹弹 Play API 客户端 |

## 修改文件

| 文件 | 变更 |
|------|------|
| `backend/src/module/parser/title_parser.py` | TMDB 搜索失败后调用 AIMatcher |
| `backend/src/module/manager/renamer.py` | 新增 dandanplay rename method，从数据库查询 dandanplay_title |
| `backend/src/module/models/config.py` | 新增 DandanplayConfig |
| `backend/src/module/models/bangumi.py` | Bangumi 和 BangumiUpdate 新增 dandanplay_title 字段 |
| `backend/src/module/database/combine.py` | 新增数据库迁移（dandanplay_title + dandanplay_retry_count） |
| `backend/src/module/core/sub_thread.py` | 新增弹弹 Play 后台补全任务 |
| `backend/src/module/conf/const.py` | 新增 dandanplay 默认配置 |
| `webui/types/config.ts` | 新增 dandanplay rename method 类型 |
| `webui/src/components/setting/config-manage.vue` | 新增 dandanplay rename method 选项 |
| `webui/src/i18n/` | 新增 dandanplay 相关翻译键 |
