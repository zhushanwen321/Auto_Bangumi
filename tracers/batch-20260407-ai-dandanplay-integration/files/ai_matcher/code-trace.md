# 代码链路分析报告

## 概述

- 分析文件：`backend/src/module/searcher/ai_matcher.py`
- 分析时间：2026-04-07
- 语言类型：Python (3.10+)
- 文件职责：基于 OpenAI LLM 的动漫标题智能匹配器，通过生成搜索关键词 -> 搜索 -> AI 择优的三步流程，为 RSS 解析流程提供兜底的番剧匹配能力。

## 调用链路图

### 上游调用方

```
RSSAnalyser.official_title_parser()
  └── (条件: settings.experimental_openai.enable == True 且 TMDB/Mikan 均匹配失败)
      └── AIMatcher.__init__(openai_config=kwargs)
          kwargs 来源: settings.experimental_openai.dict(exclude={"enable"})
          字段: api_key, api_base, api_type, api_version, model, deployment_id
      └── AIMatcher.search_and_match(
              title=bangumi.title_raw,
              search_fn=tmdb_search_fn,       # 异步函数，调用 tmdb_parser
              result_formatter=tmdb_formatter, # 同步函数，格式化候选列表
              dedup_key=lambda x: x["id"],    # 按 TMDB ID 去重
          )
```

### 内部调用链

```
AIMatcher
├── __init__(openai_config)
│   └── OpenAI(api_key, base_url)  # 同步初始化客户端
│
├── search_and_match(title, search_fn, result_formatter, dedup_key)  [async, 公开入口]
│   ├── _generate_keywords(title)              [async]
│   │   └── asyncio.to_thread(_call_llm, prompt)  # 同步 LLM 调用转异步
│   │       └── _call_llm(prompt)              [sync]
│   │           └── OpenAI.chat.completions.create()
│   │               └── json.loads(content)
│   │
│   ├── search_fn(keyword)                     [async, 外部传入]
│   │   └── (上游实现) tmdb_parser(keyword, language)
│   │
│   ├── _deduplicate(results, dedup_key)       [sync]
│   │
│   └── _pick_best_match(title, candidates, formatter)  [async]
│       └── asyncio.to_thread(_call_llm, prompt)
│           └── _call_llm(prompt)              [sync]
│               └── OpenAI.chat.completions.create()
│
├── _call_llm(prompt)                          [sync, 内部]
│   └── OpenAI.chat.completions.create(model, messages, response_format)
│       └── json.loads(response.choices[0].message.content)
│
├── _generate_keywords(title)                  [async, 内部]
├── _deduplicate(results, key_fn)              [sync, 内部]
└── _pick_best_match(title, candidates, formatter)  [async, 内部]
```

### 下游依赖

| 依赖 | 调用位置 | 类型 |
|------|---------|------|
| `openai.OpenAI` | `__init__` | 同步 HTTP 客户端 |
| `openai.chat.completions.create` | `_call_llm` | 同步 API 调用 |
| `json.loads` | `_call_llm` | 标准库 |
| `asyncio.to_thread` | `_generate_keywords`, `_pick_best_match` | 异步桥接 |

## 数据链路图

### 配置数据流

```
settings.experimental_openai (SQLModel Settings)
    │
    │  .dict(exclude={"enable"})
    ▼
openai_config: dict
    ├── api_key: str        → OpenAI(api_key=...)
    ├── api_base: str       → OpenAI(base_url=...)
    ├── model: str          → self._model (默认 "gpt-3.5-turbo")
    ├── api_type: str       → (未使用，AIMatcher 未读取)
    ├── api_version: str    → (未使用，AIMatcher 未读取)
    └── deployment_id: str  → (未使用，AIMatcher 未读取)
```

### 运行时数据流

```
输入: bangumi.title_raw (原始 RSS 标题，如 "【字幕组】葬送的芙莉莲 S01E01 1080p")
    │
    ▼ [Phase 1: 关键词生成]
KEYWORD_PROMPT.format(title=title) → LLM → {"keywords": ["葬送的芙莉莲", "Frieren", ...]}
    │
    │  逐一传入 search_fn
    ▼ [Phase 2: 搜索聚合]
tmdb_search_fn(keyword) → [{"id": 123, "title": "...", "original_title": "..."}]
    │  合并所有关键词搜索结果
    ▼ [Phase 3: 去重]
_deduplicate(all_results, key_fn=lambda x: x["id"])
    │
    ▼ [Phase 4: AI 择优]
MATCH_PROMPT.format(title=title, candidates=tmdb_formatter(results)) → LLM
    │
    ▼ {"index": 0, "confidence": 0.9}
MatchResult(matched_item=results[0], confidence=0.9)
    │
    │  返回上游
    ▼
bangumi.official_title = match.matched_item["title"]
```

### MatchResult 数据结构

```python
@dataclass
class MatchResult:
    matched_item: Any    # 搜索候选中的某一项 (dict)
    confidence: float    # LLM 返回的匹配置信度 (0-1)
```

## 链路详情

### 外部调用入口

| 入口函数 | 调用方 | 调用条件 | 文件位置 |
|---------|--------|---------|---------|
| `AIMatcher.search_and_match()` | `RSSAnalyser.official_title_parser()` | `experimental_openai.enable=True` 且 TMDB/Mikan 均失败 | `module/rss/analyser.py:71` |

### LLM 交互详情

| 调用 | 模式 | Prompt 模板 | 期望输出 | 错误处理 |
|------|------|------------|---------|---------|
| 关键词生成 | `asyncio.to_thread` | `KEYWORD_PROMPT` | `{"keywords": [...]}` | `.get("keywords", [])` 容错 |
| 最佳匹配选择 | `asyncio.to_thread` | `MATCH_PROMPT` | `{"index": N, "confidence": 0-1}` | index < 0 或 confidence < 0.7 返回 None |

### 异步处理模式

```
official_title_parser()          [async]
  └── search_and_match()         [async]
        ├── _generate_keywords()  [async]
        │     └── asyncio.to_thread(_call_llm)  # 同步 OpenAI SDK → 线程池
        │
        ├── search_fn(keyword)    [async]  # 外部传入，每个关键词间隔 0.25s
        │     └── tmdb_parser()   [async]
        │
        └── _pick_best_match()    [async]
              └── asyncio.to_thread(_call_llm)  # 同步 OpenAI SDK → 线程池
```

关键设计：`_call_llm` 是同步函数（因为 `openai` SDK 的 `create()` 是同步阻塞调用），通过 `asyncio.to_thread` 桥接到异步上下文。搜索结果之间有 0.25 秒的延迟以避免请求过于密集。

## 问题清单

### 严重问题（8-10分）

**无**

### 一般问题（5-7分）

**[P6] 配置字段不一致 -- `api_type`、`api_version`、`deployment_id` 未被使用**

`experimental_openai` 配置中有 `api_type`、`api_version`、`deployment_id` 三个字段（位于 `module/conf/const.py:48-51`），但 `AIMatcher.__init__` 只读取了 `api_key`、`api_base`、`model`。当用户配置 Azure OpenAI 等兼容服务时，这些字段不会被传递给 OpenAI 客户端，可能导致连接失败。

- 位置：`ai_matcher.py:42-48` vs `const.py:44-52`
- 建议：在 `__init__` 中将 `api_type`、`api_version`、`deployment_id` 也传入 OpenAI 客户端构造参数，或在配置校验时对未使用字段给出警告。

**[P6] `search_and_match` 中关键词搜索是串行执行，缺乏并发优化**

`search_and_match` 第 111-113 行对每个关键词逐一调用 `search_fn`，虽然有 0.25s 间隔，但所有搜索是完全串行的。如果生成了 5 个关键词，每次搜索耗时 2 秒，总耗时将达 10 秒以上。

- 位置：`ai_matcher.py:111-114`
- 建议：考虑使用 `asyncio.gather` 配合并发控制（如 semaphore 限制并发数），或使用 `asyncio.Semaphore` 实现带间隔的并发请求。

**[P5] `json.loads` 缺少异常处理**

`_call_llm` 第 58 行对 LLM 返回内容直接调用 `json.loads`，尽管使用了 `response_format={"type": "json_object"}`，但 LLM 仍可能返回无效 JSON（网络截断、模型幻觉等），会抛出 `json.JSONDecodeError` 并冒泡到 `search_and_match` 的调用方。

- 位置：`ai_matcher.py:58`
- 建议：在 `_call_llm` 中 try-except `json.JSONDecodeError`，返回空 dict `{}` 并记录日志。

### 轻微问题（1-4分）

**[P4] `OpenAI` 客户端在 `__init__` 中同步创建，不支持自定义 httpx client**

`AIMatcher.__init__` 直接 `OpenAI(api_key=..., base_url=...)` 创建客户端，这会在构造时建立连接池。在异步上下文中，应考虑传入共享的 `httpx.AsyncClient` 或使用 `AsyncOpenAI` 以避免线程池中重复创建连接。

- 位置：`ai_matcher.py:43-46`

**[P3] `_confidence_threshold` 硬编码为 0.7，不可配置**

置信度阈值写死在 `__init__` 中（第 48 行），上游 `analyser.py:78` 又重复检查了一次 `match.confidence >= 0.7`。两处阈值独立硬编码，若需调整需同时修改两处。

- 位置：`ai_matcher.py:48` 和 `analyser.py:78`
- 建议：将阈值作为 `__init__` 参数或从 `openai_config` 中读取，消除重复。

**[P2] `MatchResult.matched_item` 类型标注为 `Any`**

`MatchResult` dataclass 的 `matched_item` 字段类型为 `Any`，但实际上总是 `dict`（来自搜索结果）。使用 `Any` 降低了类型安全性。

- 位置：`ai_matcher.py:37`

**[P2] `KEYWORD_PROMPT` 要求 3-5 个关键词，但代码未校验数量**

Prompt 中写了"生成3-5个用于...搜索的关键词"，但 `_generate_keywords` 不校验返回数量。LLM 可能返回 0 个或超过 5 个关键词，影响搜索效果。

- 位置：`ai_matcher.py:60-64`

## 建议

1. **优先修复 `json.loads` 异常处理**：在 `_call_llm` 中增加 JSON 解析容错，防止 LLM 返回非法 JSON 导致整个匹配流程崩溃。

2. **补全配置字段传递**：将 `api_type`、`api_version`、`deployment_id` 传递给 OpenAI 客户端，确保 Azure OpenAI 等兼容服务可用。

3. **消除置信度阈值重复**：将 `0.7` 阈值提取为 `AIMatcher` 的构造参数，`analyser.py` 中不再重复检查。

4. **考虑关键词搜索并发化**：在保持 0.25s 间隔的前提下，可使用 `asyncio.Semaphore(2)` + `asyncio.gather` 实现有限并发，缩短总延迟。
