# 批量代码分析汇总报告

## 概述
- 批次名称：20260407-ai-dandanplay-integration
- 批次时间：2026-04-07
- 分析目录：backend/src/module（新增/修改的核心文件）
- 分析文件数：7
- 成功完成：7
- 失败：0

## 文件清单

| 文件 | Code-Trace | Issue-Trace | Review-Tracer | 状态 |
|-----|-----------|-------------|---------------|------|
| searcher/ai_matcher.py (NEW) | 0C/3M/4m | 0C/3M/4m | 8/10 | 完成 |
| searcher/dandanplay.py (NEW) | 2C/4M/3m | 0C/2M/5m | 8/10 | 完成 |
| rss/analyser.py (MOD) | 2C/3M/3m | 0C/3M/5m | 8/10 | 完成 |
| manager/renamer.py (MOD) | 1C/3M/4m | 0C/4M/4m | 8/10 | 完成 |
| core/program.py (MOD) | 0C/3M/3m | 0C/1M/4m | 8/10 | 完成 |
| core/sub_thread.py (MOD) | 0C/2M/5m | 0C/1M/6m | 7/10 | 完成 |
| api/config.py (MOD) | 0C/3M/4m | 0C/2M/5m | 8/10 | 完成 |

## 问题汇总（经 issue-trace 验证后）

### 一般问题（5-7分）

| # | 问题 | 文件 | 验证评分 | 说明 |
|---|------|------|---------|------|
| 1 | AIMatcher 不支持 Azure OpenAI | ai_matcher.py | 7/10 | 缺少 api_type/api_version/deployment_id 分支逻辑，Azure 用户无法使用 AI 匹配 |
| 2 | Mikan parser 异常处理只捕获 AttributeError | analyser.py | 6/10 | homepage=None 时 TypeError 不被捕获，导致种子解析完全失败 |
| 3 | tmdb_matched 变量语义不准确 | analyser.py | 6/10 | Mikan 成功也设 True，导致 AI 增强搜索在 Mikan 模式下无法触发 |
| 4 | _lookup_offsets 死代码 | renamer.py | 7/10 | 生产代码无调用，但测试中仍有约 10 处引用 |
| 5 | config.py asyncio.create_task fire-and-forget | config.py | 6/10 | 首次切换 rename_method 时补全任务可能被静默丢弃 |
| 6 | analyser.py asyncio.create_task 竞态条件 | analyser.py | 5/10 | ORM 对象在 session 关闭后可能被访问，有 DandanplayThread 兜底 |
| 7 | json.loads 缺少异常处理 | ai_matcher.py | 5/10 | 非法 JSON 导致 AI 匹配静默失败 |
| 8 | resp.json() 缺少 JSONDecodeError 处理 | dandanplay.py | 5/10 | API 异常响应消耗重试次数 |
| 9 | dandanplay/advance gen_path 分支重复 | renamer.py | 5/10 | 两对分支逻辑完全相同 |
| 10 | season_offset 参数传递但未使用 | renamer.py | 5/10 | 从 rename() 传递到 gen_path() 但完全不使用 |
| 11 | _batch_lookup_offsets 异常处理过宽 | renamer.py | 5/10 | Exception 兜底导致 DB 故障时偏移量静默重置为 0 |
| 12 | startup() Fire-and-Forget | program.py | 5/10 | startup 异常可能被静默吞掉 |

### 轻微问题（1-4分）

| # | 问题 | 文件 | 评分 |
|---|------|------|------|
| 13 | fetch_dandanplay_title 死代码 | dandanplay.py | 3 |
| 14 | batch_update 逐条创建 session | dandanplay.py | 3-4 |
| 15 | 置信度阈值硬编码 0.7 且重复 | ai_matcher.py | 3 |
| 16 | 串行搜索效率（设计选择） | ai_matcher.py | 5→优化 |
| 17 | DandanplayThread 无条件启动 | sub_thread.py | 4 |
| 18 | DetachedInstanceError 潜在风险 | sub_thread.py | 5→当前安全 |
| 19 | settings.dict() deprecated | config.py | 3 |
| 20 | episode_offset 计算逻辑重复 | renamer.py | 4 |

## 审查质量评估

- 平均准确性得分：8.4/10
- 平均完整性得分：7.4/10
- 平均实用性得分：8.1/10

## 链路衔接分析

### 核心数据流：AI 增强搜索
```
RSSAnalyser.official_title_parser()
  → TMDB/Mikan 搜索
    → 失败: AIMatcher.search_and_match()
      → LLM 生成关键词 → TMDB 搜索 → LLM 择优
```
**衔接状态：通畅**。AIMatcher 接口设计良好，search_fn 和 result_formatter 的抽象使得功能可复用。唯一问题是 Azure 分支缺失。

### 核心数据流：弹弹 Play 番名获取
```
DandanplayClient.search()
  → batch_update_dandanplay_titles()
    → Database session 管理写入
```
**衔接状态：基本通畅**。config.py 和 sub_thread.py 两个调用路径的 session 管理已正确处理（config.py 提取 dict，sub_thread.py 在 with 块内调用）。analyser.py 的 fire-and-forget 路径存在竞态但被 DandanplayThread 兜底。

### 核心数据流：Renamer 重命名
```
_batch_lookup_offsets()
  → RenameInfo(episode_offset, season_offset, dandanplay_title)
  → rename() 中替换 bangumi_name
  → gen_path() 生成文件名
```
**衔接状态：通畅**。RenameInfo 的 NamedTuple 设计使扩展干净整洁，dandanplay_title 的四级查找（qb_hash → tag → name → save_path）逻辑完整。

### 生命周期管理
```
Program.start()
  → dandanplay_start()
    → DandanplayThread.dandanplay_loop()
      → 24h 循环 + 条件守卫
  → dandanplay_stop()
```
**衔接状态：通畅**。MRO 链正确，start/stop 对称，与其他 Thread 模式一致。
