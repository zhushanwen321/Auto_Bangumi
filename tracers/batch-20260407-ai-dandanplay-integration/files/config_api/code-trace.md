# 代码链路分析报告

## 概述

- 分析文件：`backend/src/module/api/config.py`
- 分析时间：2026-04-07
- 语言类型：Python (FastAPI)
- 文件职责：配置管理 REST API，提供配置读取、更新端点，并在检测到 rename_method 切换到 dandanplay 时触发后台批量补全任务。

## 调用链路图

### 上游调用（谁调用了本文件）

```
HTTP Client (WebUI / curl)
  |
  +--> PATCH /api/v1/config/update  -->  update_config(config: Config)
  +--> GET  /api/v1/config/get      -->  get_config()
```

路由注册链：

```
main.py
  -> app.include_router(v1, prefix="/api")
    -> module/api/__init__.py: v1.include_router(config_router)
      -> module/api/config.py: router = APIRouter(prefix="/config")
```

### 下游调用（本文件调用了什么）

```
update_config()
  |
  +--> settings.bangumi_manage.rename_method    [读取旧配置]
  +--> _restore_masked(config.dict(), settings.dict())  [恢复脱敏字段]
  +--> settings.save(config_dict=config_dict)    [持久化配置]
  +--> settings.load()                           [重新加载配置到内存]
  +--> settings.bangumi_manage.rename_method    [读取新配置]
  +--> settings.dandanplay.enable               [读取 dandanplay 开关]
  +--> asyncio.create_task(_trigger_dandanplay_batch())  [条件触发]
        |
        +--> Database()                          [打开 DB session]
        +--> db.bangumi.get_bangumi_missing_dandanplay()  [查询缺失记录]
        +--> batch_update_dandanplay_titles(records, app_id, app_secret)
              |
              +--> DandanplayClient(app_id, app_secret)
              +--> client.search(official_title)  [逐条调用弹弹play API]
              +--> db.bangumi.update_dandanplay_title(id, title)  [写入结果]

get_config()
  |
  +--> settings.dict()          [读取全量配置]
  +--> _sanitize_dict()         [递归脱敏]
```

## 数据链路图

### update_config 数据流

```
[HTTP Request Body: Config JSON]
  |
  v
config: Config  (Pydantic 模型验证)
  |
  v
config.dict()  ->  incoming dict
settings.dict() -> current dict
  |
  v
_restore_masked(incoming, current)
  |  将 "********" 占位符替换回 current 中的真实值
  v
config_dict (完整配置，敏感字段已恢复)
  |
  v
settings.save(config_dict)  ->  写入 config/config.json
  |
  v
settings.load()  ->  从文件重新加载到 settings 单例内存
  |
  v
old_method vs new_method 比较
  |  old_method: save 之前从 settings 读取
  |  new_method: load 之后从 settings 读取
  v
[条件分支] old_method 不在 dandanplay 相关值中
            AND new_method 在 ("dandanplay", "subtitle_dandanplay") 中
            AND settings.dandanplay.enable == True
            |
            v
          触发 _trigger_dandanplay_batch()
```

### _trigger_dandanplay_batch 数据流

```
[触发条件满足]
  |
  v
with Database() as db:
  records = db.bangumi.get_bangumi_missing_dandanplay()
  |  SQL: SELECT * FROM bangumi
  |       WHERE dandanplay_title IS NULL
  |         AND dandanplay_retry_count < 3
  |         AND deleted = FALSE
  v
record_data = [{"id": r.id, "official_title": r.official_title} for r in records]
  |  ORM 对象 -> 纯 dict，避免 detach 问题
  v
await batch_update_dandanplay_titles(
    records=record_data,         # list[dict]
    app_id=settings.dandanplay.app_id,
    app_secret=settings.dandanplay.app_secret,
)
  |
  v
  for record in records:
    record["id"], record["official_title"]  # dict 访问
    |
    v
    title = await client.search(official_title)
    |  HTTP GET https://api.dandanplay.net/api/v2/search/anime
    |  Headers: X-AppId, X-Timestamp, X-Signature (HMAC-SHA256)
    v
    with Database() as db:
      db.bangumi.update_dandanplay_title(record_id, title)
      |  title != None: dandanplay_title = title, retry_count = 0
      |  title == None: dandanplay_title = NULL, retry_count += 1
      v
    _invalidate_bangumi_cache()  # 清除模块级缓存
```

### get_config 数据流

```
settings.dict()  ->  全量配置 dict
  |
  v
_sanitize_dict(d)
  |  递归遍历所有 key
  |  若 key 包含 password/api_key/token/secret 且 value 是 str -> 替换为 "********"
  v
JSONResponse  ->  脱敏后的配置
```

## 链路详情

| 序号 | 函数 | 调用目标 | 说明 |
|------|------|----------|------|
| 1 | `update_config` | `settings.bangumi_manage.rename_method` | 读取旧 rename_method（第 96 行） |
| 2 | `update_config` | `_restore_masked` | 恢复前端传回的脱敏占位符为真实值 |
| 3 | `update_config` | `settings.save` | 将 config_dict 写入 JSON 文件 |
| 4 | `update_config` | `settings.load` | 从文件重新加载到内存单例 |
| 5 | `update_config` | `asyncio.create_task` | Fire-and-forget 后台任务 |
| 6 | `_trigger_dandanplay_batch` | `Database()` | 上下文管理器，获取 DB session |
| 7 | `_trigger_dandanplay_batch` | `get_bangumi_missing_dandanplay` | 查询需要补全的番剧记录 |
| 8 | `_trigger_dandanplay_batch` | `batch_update_dandanplay_titles` | 批量调用弹弹 play API 补全 |
| 9 | `batch_update_dandanplay_titles` | `DandanplayClient.search` | HTTP 请求弹弹 play 搜索 API |
| 10 | `batch_update_dandanplay_titles` | `update_dandanplay_title` | 将结果写入数据库 |
| 11 | `get_config` | `settings.dict` / `_sanitize_dict` | 读取并脱敏配置 |

## 问题清单

### 严重问题（8-10分）

**无严重问题。**

### 一般问题（5-7分）

#### P1: asyncio.create_task 的生命周期不可控 -- 评分 6

`update_config` 第 110 行使用 `asyncio.create_task(_trigger_dandanplay_batch())`，这是一个 fire-and-forget 模式：

- **问题**：如果服务在 task 完成前重启/关闭，批量补全会被静默丢弃，无任何日志或持久化标记。
- **影响**：用户以为补全在执行，实际上可能丢失。批量补全可能是长时间运行的操作（每条记录一次 HTTP 请求），如果在运行中途服务关闭，已完成的记录不会重试，未完成的也不会被标记。
- **改进建议**：将 task 引用保存到应用状态中，在 `lifespan` shutdown 时 `await task`，或使用更健壮的任务队列。

#### P2: _trigger_dandanplay_batch 中延迟导入的设计意图不明确 -- 评分 5

第 67-68 行在函数内部执行 `from module.database import Database` 和 `from module.searcher.dandanplay import batch_update_dandanplay_titles`。

- **问题**：延迟导入会增加函数调用时的开销，且如果导入失败（如模块缺失），错误会被外层 `except Exception` 吞掉，用户只会看到 "Batch update failed" 而不知道是依赖缺失。
- **影响**：调试困难，掩盖真正的错误原因。
- **改进建议**：如果是为了避免循环导入，应在注释中说明；否则应移到文件顶部。异常处理应区分 ImportError 和运行时错误。

#### P3: settings.dict() 方法不存在于 Settings 类 -- 评分 6

`get_config()` 第 61 行调用 `settings.dict()`，但 `Settings` 类（继承自 `Config`，后者继承自 `BaseModel`）没有定义 `dict()` 方法。Pydantic v2 中 `dict()` 已被弃用，应使用 `model_dump()`。

- **问题**：如果 Pydantic 版本 >= 2.0，`dict()` 可能产生 DeprecationWarning 或在未来版本中移除。当前代码能运行是因为 Pydantic v2 仍保留向后兼容的 `dict()` 别名。
- **影响**：未来 Pydantic 升级可能导致运行时错误。
- **改进建议**：改用 `settings.model_dump()`。

### 轻微问题（1-4分）

#### M1: update_config 中 save 和 load 之间存在短暂的不一致窗口 -- 评分 3

第 98-99 行先 `save` 再 `load`，`old_method` 在第 96 行读取（save 之前），`new_method` 在第 104 行读取（load 之后）。

- **问题**：如果 `load()` 失败（文件损坏、权限问题），`old_method` 已读取但 `new_method` 无法获取，会进入 `except` 分支返回 406，但此时配置文件已经被 `save()` 写入了新值，导致文件和内存不一致。
- **影响**：低概率，但可能导致配置文件已更新但应用仍使用旧配置，直到下次重启。
- **改进建议**：先 load 验证成功后再 save，或使用事务性写入（写临时文件再原子替换）。

#### M2: _restore_masked 不处理嵌套 list 中的非 dict 元素中的敏感字段 -- 评分 2

`_restore_masked` 第 46-52 行只处理 list 中嵌套的 dict 元素，对于 list 中的字符串值（如 `["password_value"]`）不会恢复。

- **问题**：当前配置模型中没有 list 类型的敏感字段，所以实际不会触发，但逻辑上不够通用。
- **影响**：目前无实际影响。

#### M3: batch_update_dandanplay_titles 中对 record 的类型判断冗余 -- 评分 2

第 85-89 行使用 `hasattr(record, "id")` 来判断是 ORM 对象还是 dict，但调用方 `_trigger_dandanplay_batch` 总是传入纯 dict（第 77-79 行已做了 ORM -> dict 转换）。

- **问题**：`batch_update_dandanplay_titles` 中的 `hasattr` 分支永远不会走 ORM 路径，增加了不必要的代码复杂度。
- **影响**：代码可读性下降。
- **改进建议**：要么统一类型为 dict 并移除 hasattr 分支，要么在函数签名中使用 TypedDict 明确类型。

#### M4: _sanitize_dict 中的敏感词匹配过于宽泛 -- 评分 2

第 14 行 `_SENSITIVE_KEYS = ("password", "api_key", "token", "secret")`，第 19 行使用 `any(s in key.lower() for s in _SENSITIVE_KEYS)`。

- **问题**：子串匹配可能导致误脱敏，例如 `password_hint`、`token_count`、`api_key_type` 等字段会被误脱敏。
- **影响**：当前配置模型中没有此类字段名，但未来扩展可能触发。

## 重点分析

### _trigger_dandanplay_batch 的触发条件

触发条件（第 105-109 行）：

```
old_method NOT IN ("dandanplay", "subtitle_dandanplay")
AND new_method IN ("dandanplay", "subtitle_dandanplay")
AND settings.dandanplay.enable == True
```

这是一个「首次切换到 dandanplay」的检测逻辑。设计意图是：只在用户第一次启用 dandanplay 重命名方法时触发全量补全。如果用户从 "dandanplay" 切换到 "subtitle_dandanplay"（或反之），不会触发。

**潜在问题**：如果用户在 dandanplay 模式下添加了新番剧（这些番剧没有 dandanplay_title），再次调用 update_config 不会触发补全，因为 old_method 已经是 "dandanplay"。新番剧的补全依赖 `sub_thread.py` 中的增量补全逻辑。

### record_data 提取逻辑

第 77-79 行将 ORM 对象转换为纯 dict：

```python
record_data = [
    {"id": r.id, "official_title": r.official_title} for r in records
]
```

**设计原因**：`records` 是在 `with Database() as db:` 上下文内查询的 ORM 对象，离开上下文后 session 关闭，ORM 对象会 detach（变为 detached state），后续访问属性可能触发 `DetachedInstanceError`。转换为 dict 后数据独立于 session，可安全传递。

**评价**：这是正确的做法，避免了 SQLAlchemy 经典的 detached instance 问题。

### 与 batch_update_dandanplay_titles 的参数衔接

- `_trigger_dandanplay_batch` 传入 `records=record_data`（list[dict]），每个 dict 包含 `id` 和 `official_title` 两个 key。
- `batch_update_dandanplay_titles` 接收 `records: list`，内部通过 `hasattr` 判断访问方式，dict 路径使用 `record["id"]` 和 `record["official_title"]`。
- 参数衔接正确，类型匹配。

### old_method / new_method 比较逻辑

- `old_method` 在 `settings.save()` 之前读取（第 96 行），此时 settings 内存中仍是旧值。
- `new_method` 在 `settings.load()` 之后读取（第 104 行），此时 settings 内存已更新为新值。
- 比较逻辑使用集合判断，覆盖了 "dandanplay" 和 "subtitle_dandanplay" 两种 dandanplay 相关方法。

## 建议

1. **P1 修复**：将 `asyncio.create_task` 的返回值保存到应用状态，在 FastAPI lifespan 的 shutdown 阶段 await 该 task，确保服务关闭时批量补全任务能优雅结束。
2. **P2 修复**：将延迟导入移到文件顶部，或在 except 中单独捕获 ImportError 并提供明确的错误信息。
3. **P3 修复**：将 `settings.dict()` 替换为 `settings.model_dump()`，保持与 Pydantic v2 一致。
4. **M1 修复**：将 save 和 load 合并为原子操作，或至少在 load 失败时回滚 save 的变更。
