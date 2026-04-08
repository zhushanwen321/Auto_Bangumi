# 问题链路分析报告

## 概述
- 分析文件：`backend/src/module/searcher/dandanplay.py`
- 基于报告：`tracers/batch-20260407-ai-dandanplay-integration/files/dandanplay/code-trace.md`
- 分析时间：2026-04-07
- 验证问题数量：8

## 问题验证结果

### 问题 1：sub_thread.py 传递已 detach 的 ORM 对象（报告评分 9/10）

#### 问题存在性：不存在

报告声称 `sub_thread.py:232-239` 中 `with Database() as db:` 上下文退出后 ORM 对象处于 detached 状态。经验证，`await batch_update_dandanplay_titles(records=records, ...)` 的调用位于 `with Database() as db:` 块**内部**（sub_thread.py:232 进入 with，239 行 await 仍在 if records 分支内，属于 with 块的作用域）。在整个 `batch_update_dandanplay_titles` 执行期间（包括 for 循环的逐条处理），外层 Database session 一直保持活跃状态。

此外，同步 engine 使用 `create_engine(DATA_PATH)` 创建，SQLAlchemy 默认 `expire_on_commit=True`。但此处并未 commit 外层 session，所以不存在属性过期问题。

真正的 detached 风险存在于 analyser.py 的 `asyncio.create_task` 场景（见问题 2），而非 sub_thread.py。

#### 严重程度评估：1/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 1 | 不存在，records 在 session 活跃期间被使用 |
| 触发概率 | 1 | 不可能触发 |
| 后果严重性 | 1 | 无后果 |
| 描述准确性 | 1 | 代码结构判断错误，误判了 with 块的作用域 |

#### 验证链路

```
sub_thread.py:232  with Database() as db:          # session 开始
sub_thread.py:233      records = db.bangumi.get_bangumi_missing_dandanplay()
sub_thread.py:234      if records:                  # 仍在 with 块内
sub_thread.py:239          await batch_update_dandanplay_titles(  # session 仍然活跃
sub_thread.py:240              records=records,     # ORM 对象可安全访问
sub_thread.py:241-243          ...
                          )                         # await 完成后才继续
                      # with 块在此之后才退出
```

---

### 问题 2：rss/analyser.py 中异步任务生命周期未管理（报告评分 8/10）

#### 问题存在性：存在

`analyser.py:137` 调用 `self._fetch_dandanplay_titles(new_data)`，该方法在第 163 行使用 `asyncio.create_task(_do_fetch())` 创建后台任务但不保存引用。

验证链路：
1. `sub_thread.py:30` 中 `with RSSEngine() as engine:` 创建 session
2. `analyser.py:135` 执行 `engine.bangumi.add_all(new_data)`（内部会 commit）
3. `analyser.py:137` 调用 `self._fetch_dandanplay_titles(new_data)`（同步方法）
4. `analyser.py:163` 内部 `asyncio.create_task(_do_fetch())` 创建后台协程
5. 控制权返回 `rss_to_data`，继续处理下一个 rss，最终 `with RSSEngine()` 块退出，session 关闭
6. 后台 task 中的 `batch_update_dandanplay_titles` 此时才真正开始执行 `for` 循环
7. 此时 `new_data` 中的 ORM 对象已 detached

但实际影响有限：`batch_update_dandanplay_titles` 内部只读取 `record.id` 和 `record.official_title`。由于 `add_all` 内部执行了 commit（bangumi.py:212），而 `expire_on_commit=True`（默认值），commit 后属性会被 expire。但 `add_all` 的 commit 在 `with RSSEngine()` 块内完成，此时 session 仍活跃，所以属性会在下次访问时自动重新加载。

关键问题在于：当 `asyncio.create_task` 的任务实际执行时（在 event loop 的下一个迭代），`with RSSEngine()` 块可能已经退出。此时访问已 expire 且 session 已关闭的 ORM 属性，会抛出 `DetachedInstanceError`。

不过这里有一个微妙的时序问题：`asyncio.create_task` 只是将协程加入调度队列，实际执行取决于 event loop。在当前同步代码路径中（`_fetch_dandanplay_titles` 是 `@staticmethod`，不是 async），`create_task` 之后函数立即返回，但 event loop 要等当前协程让出控制权（下一个 `await`）时才会执行新 task。而 `rss_to_data` 的调用者在 `with RSSEngine()` 块内，后续还有 `await engine.refresh_rss(client)` 等操作。所以 task 可能在 session 仍然活跃时就开始执行了。

**结论**：这是一个竞态条件问题，是否触发取决于 event loop 的调度时序。在正常负载下大概率安全（task 在 session 活跃期间就开始执行 for 循环的第一个 await），但在高负载或特定时序下可能触发 `DetachedInstanceError`。

#### 严重程度评估：5/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 4 | 仅影响新增番剧后首次弹弹 Play 番名获取 |
| 触发概率 | 4 | 竞态条件，大多数情况安全，特定时序下可能触发 |
| 后果严重性 | 5 | DetachedInstanceError 会导致该批次的弹弹 Play 番名获取失败，但不会崩溃（被上层 try-except 捕获） |
| 描述准确性 | 7 | 问题方向正确但遗漏了竞态条件的分析，直接断言"会 detach"过于绝对 |

#### 验证链路

```
sub_thread.py:30       with RSSEngine() as engine:   # session A 开始
sub_thread.py:34           await self.analyser.rss_to_data(rss, engine)
analyser.py:135                engine.bangumi.add_all(new_data)  # commit, 属性 expire
analyser.py:137                self._fetch_dandanplay_titles(new_data)  # 同步调用
analyser.py:163                    asyncio.create_task(_do_fetch())  # 调度后台任务
                                   # 控制权返回 rss_to_data
sub_thread.py:36               await engine.refresh_rss(client)  # await, event loop 可能在此时执行 task
                               # ... session A 仍活跃 ...
                               # with 块结束, session A 关闭
                               # 后台 task 如果此时才执行, new_data 已 detached
```

---

### 问题 3：batch_update_dandanplay_titles 中每个 record 单独创建 Database session（报告评分 7/10）

#### 问题存在性：存在

验证确认 `batch_update_dandanplay_titles` 在 for 循环内每次迭代都执行 `with Database() as db:`（dandanplay.py:93 正常路径，dandanplay.py:105 异常路径）。对于 N 条记录会创建 2N 个 session（最坏情况，每条都异常）。

#### 严重程度评估：4/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 3 | 性能问题，不影响正确性 |
| 触发概率 | 10 | 每次批量更新都必然触发 |
| 后果严重性 | 2 | SQLite 场景下连接开销较小；原子性缺失但后台任务场景可接受 |
| 描述准确性 | 9 | 描述准确 |

#### 验证链路

```
dandanplay.py:84  for record in records:
dandanplay.py:92      title = await client.search(official_title)  # 网络请求
dandanplay.py:93      with Database() as db:   # session 1
dandanplay.py:94          db.bangumi.update_dandanplay_title(record_id, title)
                      # session 1 关闭
dandanplay.py:84  for record in records:  # 下一条
dandanplay.py:93      with Database() as db:   # session 2
                      # ...
```

---

### 问题 4：HTTP 响应 JSON 解析无异常处理（报告评分 6/10）

#### 问题存在性：存在

`dandanplay.py:56` 的 `resp.json()` 未被 try-except 包裹在 JSON 解析层面。`httpx.JSONDecodeError` 继承自 `json.JSONDecodeError`，不继承 `httpx.HTTPError`，所以不会被第 62 行的 `except httpx.HTTPError` 捕获。

如果 API 返回非 JSON 内容（如 502 网关错误返回 HTML），`resp.json()` 会抛出异常，被 `batch_update_dandanplay_titles` 的 `except Exception as e` 捕获，导致 `update_dandanplay_title(record_id, None)` 被调用，递增 `dandanplay_retry_count`。

#### 严重程度评估：5/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 4 | 影响所有调用 search 的场景 |
| 触发概率 | 3 | 弹弹 Play API 通常返回 JSON，只有在服务端异常时才可能返回非 JSON |
| 后果严重性 | 5 | 临时服务端故障会消耗重试次数，3 次后不再重试，导致永久缺失番名 |
| 描述准确性 | 9 | 描述准确，因果链完整 |

#### 验证链路

```
dandanplay.py:56  data = resp.json()
    # 如果 API 返回 HTML 错误页面:
    #   -> httpx.JSONDecodeError (不继承 httpx.HTTPError)
    #   -> 不被 dandanplay.py:62 的 except httpx.HTTPError 捕获
    #   -> 异常传播到 batch_update_dandanplay_titles
dandanplay.py:103 except Exception as e:
dandanplay.py:105     with Database() as db:
dandanplay.py:106         db.bangumi.update_dandanplay_title(record_id, None)
                          # None -> dandanplay_retry_count += 1 (bangumi.py:701)
                          # 3 次后永久跳过 (get_bangumi_missing_dandanplay 条件: retry_count < 3)
```

---

### 问题 5：search() 方法仅返回第一个结果的 animeTitle（报告评分 6/10）

#### 问题存在性：存在

`dandanplay.py:59` 确实使用 `animes[0].get("animeTitle")`，无匹配度验证。但这是弹弹 Play 搜索 API 的使用方式——传入的是 `official_title`（已通过 TMDB/Mikan 解析的标准番名），搜索结果的第一条通常就是正确匹配。

#### 严重程度评估：3/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 3 | 可能导致错误番名写入 |
| 触发概率 | 2 | official_title 通常是标准名称，搜索结果首条基本正确 |
| 后果严重性 | 3 | 错误番名会导致重命名失败，retry_count 被重置为 0，不会自动纠正 |
| 描述准确性 | 7 | 问题描述正确但高估了实际触发概率 |

---

### 问题 6：generate_signature 使用字符串拼接而非结构化签名（报告评分 5/10）

#### 问题存在性：存在（但非本项目问题）

签名格式 `f"{app_id}{timestamp}{path}{app_secret}"` 是弹弹 Play API 的协议定义，本项目无法修改。报告自身也承认了这一点。

#### 严重程度评估：1/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 1 | 不可修改的第三方协议 |
| 触发概率 | 1 | 理论碰撞风险，实际中各字段长度固定 |
| 后果严重性 | 1 | N/A |
| 描述准确性 | 3 | 描述了真实情况但作为"问题"列出没有实际意义 |

---

### 问题 7：fetch_dandanplay_title 是死代码（报告评分 4/10）

#### 问题存在性：存在

全代码库搜索确认：`fetch_dandanplay_title` 在生产代码中无任何调用者。三个调用者（config.py、analyser.py、sub_thread.py）都直接调用 `batch_update_dandanplay_titles`。仅在 `test/test_dandanplay_fetch.py` 中被测试引用。

#### 严重程度评估：3/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 2 | 死代码不影响运行时行为 |
| 触发概率 | 1 | 不触发 |
| 后果严重性 | 1 | 无运行时影响，仅增加代码维护负担 |
| 描述准确性 | 10 | 完全准确 |

#### 验证链路

```
grep "fetch_dandanplay_title" 结果:
  - dandanplay.py:67  定义
  - analyser.py:137  不相关（调用的是 batch_update，不是 fetch）
  - test_dandanplay_fetch.py  仅测试代码引用

三个生产调用者全部使用 batch_update_dandanplay_titles:
  - api/config.py:81    batch_update_dandanplay_titles(records=record_data, ...)
  - rss/analyser.py:157  batch_update_dandanplay_titles(records=bangumi_list, ...)
  - core/sub_thread.py:239 batch_update_dandanplay_titles(records=records, ...)
```

---

### 问题 8：batch_update_dandanplay_titles 中异常处理过于宽泛（报告评分 3/10）

#### 问题存在性：存在

`dandanplay.py:103` 使用 `except Exception as e` 捕获所有异常。在后台任务场景中这是常见做法，但确实会掩盖编程错误。

#### 严重程度评估：2/10
| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 2 | 可能掩盖编程错误的调试信息 |
| 触发概率 | 2 | 仅在存在编程错误时触发 |
| 后果严重性 | 2 | bug 被静默吞掉，增加调试难度 |
| 描述准确性 | 9 | 描述准确 |

---

## 总结

| 问题 | 报告评分 | 验证评分 | 评级 |
|-----|---------|---------|------|
| P1: sub_thread.py detached ORM | 9 | 1 | 误报 |
| P1: analyser.py 异步任务生命周期 | 8 | 5 | 低风险竞态 |
| P2: 每 record 单独 session | 7 | 4 | 轻微 |
| P2: resp.json() 无异常处理 | 6 | 5 | 低风险 |
| P2: search() 仅取第一个结果 | 6 | 3 | 轻微 |
| P2: 签名拼接无分隔符 | 5 | 1 | 非问题 |
| P3: fetch_dandanplay_title 死代码 | 4 | 3 | 轻微 |
| P3: 异常处理过于宽泛 | 3 | 2 | 轻微 |

### 统计
- 真实严重问题（8-10分）：0 个
- 部分存在问题（5-7分）：2 个（analyser.py 竞态条件、resp.json() 异常处理）
- 虚假/轻微问题（1-4分）：6 个（含 1 个误报、1 个非本项目问题）

### 关键发现

报告最大的判断失误在于 **问题 1（sub_thread.py detached ORM）**。通过验证代码缩进确认 `await batch_update_dandanplay_titles` 在 `with Database() as db:` 块内部执行，session 在整个批量操作期间保持活跃。这个 9 分的"严重问题"实际不存在。

真正的 detached 风险在 **问题 2（analyser.py）** 中，但由于 `asyncio.create_task` 的调度时序特性，实际触发概率较低。`api/config.py` 已经正确处理了这个问题（提取为 dict 后传递），说明开发者意识到了 detached 风险，只是 analyser.py 的处理不够严谨。
