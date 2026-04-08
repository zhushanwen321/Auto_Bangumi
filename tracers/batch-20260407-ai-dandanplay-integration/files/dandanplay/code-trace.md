# 代码链路分析报告

## 概述
- 分析文件：`backend/src/module/searcher/dandanplay.py`
- 分析时间：2026-04-07
- 语言类型：Python (async)

## 调用链路图

### 下游调用链

```
dandanplay.py
├── generate_signature()
│   ├── hashlib.sha256()          # 标准库
│   └── base64.b64encode()        # 标准库
│
├── DandanplayClient.__init__()
│   └── (无下游调用)
│
├── DandanplayClient._build_headers()
│   ├── time.time()               # 标准库
│   └── generate_signature()      # 模块内函数
│
├── DandanplayClient.search()
│   ├── self._build_headers()     # 实例方法
│   └── httpx.AsyncClient.get()   # 第三方 HTTP 库
│
├── fetch_dandanplay_title()
│   ├── DandanplayClient()        # 构造客户端
│   └── client.search()           # 实例方法
│
└── batch_update_dandanplay_titles()
    ├── DandanplayClient()        # 构造客户端
    ├── client.search()           # 逐条搜索
    └── Database()                # 数据库操作
        └── db.bangumi.update_dandanplay_title()
            ├── self.search_id()       # 查询 bangumi 记录
            ├── self.session.commit()  # 提交事务
            └── _invalidate_bangumi_cache()  # 清除缓存
```

### 上游调用链

```
调用者 1: module/api/config.py::_trigger_dandanplay_batch()
    │  触发时机: 用户更新配置后
    │  传递数据: records = [{"id": r.id, "official_title": r.official_title}, ...]  (dict 列表)
    └─→ batch_update_dandanplay_titles(records, app_id, app_secret)

调用者 2: module/rss/analyser.py::_fetch_dandanplay_titles()
    │  触发时机: 新增番剧后后台异步获取
    │  传递数据: records = bangumi_list  (Bangumi ORM 对象列表)
    │  调用方式: asyncio.create_task(_do_fetch())
    └─→ batch_update_dandanplay_titles(records, app_id, app_secret)

调用者 3: module/core/sub_thread.py::DandanplayThread
    │  触发时机: 后台定时循环 (24小时间隔)
    │  传递数据: records = db.bangumi.get_bangumi_missing_dandanplay()  (Bangumi ORM 对象列表)
    └─→ batch_update_dandanplay_titles(records, app_id, app_secret)
```

### fetch_dandanplay_title 上游

```
无上游调用者。该函数在当前代码库中未被任何模块引用，属于死代码。
```

## 数据链路图

### API 签名认证流程

```
输入数据:
  app_id (str)       ← settings.dandanplay.app_id ← config["dandanplay"]["app_id"]
  app_secret (str)   ← settings.dandanplay.app_secret ← config["dandanplay"]["app_secret"]

签名生成:
  timestamp = int(time.time())
  data = f"{app_id}{timestamp}{path}{app_secret}"
  sha256_hash = hashlib.sha256(data.encode()).digest()    # 32 字节原始二进制
  signature = base64.b64encode(sha256_hash).decode()       # 44 字符 Base64 字符串

HTTP Headers:
  X-AppId:      app_id
  X-Timestamp:  timestamp (秒级整数)
  X-Signature:  signature (Base64 编码的 SHA256 摘要)
```

### HTTP 请求处理数据流

```
DandanplayClient.search(keyword):
  URL:     https://api.dandanplay.net/api/v2/search/anime
  Method:  GET
  Params:  keyword=<keyword>&withRelated=false
  Headers: X-AppId, X-Timestamp, X-Signature
  Timeout: 10 秒

  响应处理:
    status != 200  → return None (warning 日志)
    正常响应:
      data = resp.json()
      animes = data.get("animes", [])
      return animes[0].get("animeTitle") if animes else None

  异常处理:
    httpx.HTTPError → return None (warning 日志)
    注意: 未捕获 json 解析异常 (JSONDecodeError, KeyError 等)
```

### batch_update 数据库 Session 管理模式

```
batch_update_dandanplay_titles(records, app_id, app_secret):
  │
  ├─ 创建一个 DandanplayClient 实例 (共享 app_id/secret)
  │
  ├─ FOR EACH record in records:
  │    │
  │    ├─ 提取 record_id 和 official_title
  │    │   (通过 hasattr 判断是 ORM 对象还是 dict)
  │    │
  │    ├─ title = await client.search(official_title)
  │    │
  │    ├─ [正常路径]
  │    │   with Database() as db:              ← 每条记录新建独立 session
  │    │       db.bangumi.update_dandanplay_title(record_id, title)
  │    │                                       ← 内部: search_id → 修改 → commit → 清缓存
  │    │
  │    └─ [异常路径]
  │        with Database() as db:              ← 异常时也新建独立 session
  │            db.bangumi.update_dandanplay_title(record_id, None)
  │                                         ← None 会递增 dandanplay_retry_count
  │
  └─ 循环结束 (无总体错误聚合)
```

## 链路详情

### 关键数据表

| 数据项 | 类型 | 来源 | 用途 |
|--------|------|------|------|
| `app_id` | str | 配置文件 `config["dandanplay"]["app_id"]` | 弹弹 Play API 身份标识 |
| `app_secret` | str | 配置文件 `config["dandanplay"]["app_secret"]` | 签名密钥 |
| `keyword` / `official_title` | str | Bangumi ORM `official_title` 字段 | 搜索关键词 |
| `animeTitle` | str (Optional) | 弹弹 Play API 响应 | 匹配的番名 |
| `dandanplay_title` | str (Optional) | Bangumi 数据库字段 | 存储匹配结果 |
| `dandanplay_retry_count` | int | Bangumi 数据库字段, 默认 0 | 失败重试计数, >=3 不再重试 |

### 各调用者数据传递对比

| 调用者 | records 类型 | session 管理方 | 潜在风险 |
|--------|-------------|---------------|---------|
| `api/config.py` | `list[dict]` (已提取纯数据) | config.py 先查后传, batch_update 内部写 | 安全 |
| `rss/analyser.py` | `list[Bangumi]` (ORM 对象) | analyser 无独立 session, batch_update 内部写 | **ORM 对象可能已 detach** |
| `sub_thread.py` | `list[Bangumi]` (ORM 对象) | sub_thread 的 `with Database()` 已退出, batch_update 内部写 | **ORM 对象已 detach** |

## 问题清单

### 严重问题 (8-10分)

**[P1 - 9分] sub_thread.py 传递已 detach 的 ORM 对象**

`sub_thread.py:232-239` 中，`with Database() as db:` 上下文退出后 session 已关闭，`records` 中的 ORM 对象处于 detached 状态。`batch_update_dandanplay_titles` 内部通过 `hasattr(record, "id")` 判断为 ORM 对象并直接访问 `record.id` 和 `record.official_title`。

SQLAlchemy ORM 对象在 session 关闭后访问已加载的标量属性通常是安全的（因为值已被填充到实例的 `__dict__` 中），但这是一个脆弱的隐式依赖。如果 `get_bangumi_missing_dandanplay()` 使用了 `expire_on_commit=False` 或者属性被 lazy load，就会抛出 `DetachedInstanceError`。

`api/config.py` 已经意识到了这个问题并做了正确的处理（提取为 dict），但 `sub_thread.py` 没有。

**[P1 - 8分] rss/analyser.py 中异步任务生命周期未管理**

`analyser.py:163` 使用 `asyncio.create_task(_do_fetch())` 创建后台任务，但没有保存 task 引用。如果任务在 event loop 关闭前未完成，会产生 "Task was destroyed but it is pending" 警告。且 `_do_fetch` 内部调用的 `batch_update_dandanplay_titles` 的异常会被 asyncio 吞掉，不会打印任何日志。

### 一般问题 (5-7分)

**[P2 - 7分] batch_update_dandanplay_titles 中每个 record 单独创建 Database session**

每条记录都执行 `with Database() as db:`，对于 N 条记录会创建 N 个独立 session 和事务。这既影响性能（反复开关连接），又破坏了原子性——部分记录更新成功、部分失败时，数据库处于不一致状态。

**[P2 - 6分] HTTP 响应 JSON 解析无异常处理**

`DandanplayClient.search()` 中 `resp.json()` 没有 try-except 包裹。如果弹弹 Play API 返回非 JSON 内容（如 HTML 错误页面、空响应），会抛出 `httpx.JSONDecodeError`，该异常不属于 `httpx.HTTPError` 子类，不会被外层 catch 捕获，会导致 `batch_update_dandanplay_titles` 中的单条异常处理路径被触发，写入 None 并递增 retry_count——这可能是非预期的行为（网络或服务端临时故障不应消耗重试次数）。

**[P2 - 6分] search() 方法仅返回第一个结果的 animeTitle**

`animes[0].get("animeTitle")` 始终取第一个搜索结果，没有做匹配度验证。如果关键词搜索返回了不相关的结果，会写入错误的番名，且 retry_count 被重置为 0，后续不会再重试。

**[P2 - 5分] generate_signature 使用字符串拼接而非结构化签名**

签名输入为 `f"{app_id}{timestamp}{path}{app_secret}"`，各字段之间无分隔符。如果 app_id 或 path 的值变化导致拼接后产生歧义（例如 app_id="abc" + timestamp="123" 与 app_id="abc1" + timestamp="23" 产生相同前缀），可能存在理论上的碰撞风险。不过这是弹弹 Play API 的协议定义，不是本项目可以修改的。

### 轻微问题 (1-4分)

**[P3 - 4分] fetch_dandanplay_title 是死代码**

该函数在整个代码库中没有被任何模块调用。三个调用者都直接使用 `batch_update_dandanplay_titles`。这个函数可能是早期设计的遗留。

**[P3 - 3分] batch_update_dandanplay_titles 中异常处理过于宽泛**

`except Exception as e` 捕获了所有异常。虽然这在后台任务中是常见做法，但会掩盖编程错误（如 TypeError、AttributeError）。建议至少区分 `httpx.HTTPError`（网络问题）和其他异常。

**[P3 - 2分] DandanplayClient.search 每次调用创建新的 httpx.AsyncClient**

`async with httpx.AsyncClient(timeout=10) as client:` 在每次 search 调用时创建新的 client 实例。虽然 `batch_update` 中已经复用了 `DandanplayClient`，但底层的 HTTP 连接没有复用（每个请求都会建立新的 TCP+TLS 连接）。对于批量操作，应该复用 `httpx.AsyncClient`。

## 建议

### 优先修复

1. **统一 sub_thread.py 的数据传递方式**：参照 `api/config.py` 的做法，在 `with Database()` 上下文内将 ORM 对象转换为 dict 后再传递给 `batch_update_dandanplay_titles`，消除 detached ORM 对象的隐式依赖。

2. **batch_update 内部使用单一 session**：将 `with Database() as db:` 提到循环外部，整个批量操作共用一个 session 和事务。这样既提升性能，又保证原子性。异常时整体回滚，而不是部分写入。

3. **为 resp.json() 添加异常处理**：在 `DandanplayClient.search()` 中将 `resp.json()` 包裹在 try-except 中，捕获 `httpx.JSONDecodeError`，返回 None 而非让异常向上传播。

### 建议改进

4. **保存 asyncio.create_task 的引用**：在 `rss/analyser.py` 中将 task 保存到实例属性或集合中，防止任务被静默丢弃。

5. **删除或标记 fetch_dandanplay_title**：如果确认是死代码，直接删除；如果预留给未来使用，添加 `@deprecated` 或注释说明。

6. **复用 httpx.AsyncClient**：在 `DandanplayClient` 中将 `httpx.AsyncClient` 作为实例属性，通过 `async with` 生命周期管理，所有 search 请求共享连接池。
