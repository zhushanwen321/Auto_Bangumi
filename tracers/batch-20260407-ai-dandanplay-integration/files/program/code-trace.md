# 代码链路分析报告

## 概述

- 分析文件：`backend/src/module/core/program.py`
- 分析时间：2026-04-07
- 语言类型：Python
- 文件职责：应用主控制器，通过多重继承组合所有后台线程，编排启动/停止/重启生命周期

## 调用链路图

### MRO 继承链（Python C3 线性化）

```
Program
  -> DandanplayThread   (最右侧，MRO 最先解析)
    -> CalendarRefreshThread
      -> OffsetScanThread
        -> RenameThread
          -> RSSThread
            -> ProgramStatus
              -> Checker
                -> object
```

每个 `__init__` 中的 `super().__init__()` 沿 MRO 链依次调用，确保所有基类被初始化。`Program.__init__` 仅额外设置 `_startup_done` 标志。

### 下游调用链

```
Program.startup()
  ├── first_run()                    # module/update.py - 首次运行初始化
  ├── data_migration()               # module/update.py - 旧数据迁移
  ├── from_30_to_31()                # module/update.py - 3.0→3.1 迁移
  ├── from_31_to_32()                # module/update.py - 3.1→3.2 迁移
  ├── run_migrations()               # module/update.py - Schema 版本迁移
  ├── cache_image()                  # module/update.py - 图片缓存构建
  └── Program.start()
        ├── settings.load()          # module/conf - 重新加载配置
        ├── self.check_downloader_status()  # Checker - 循环检测下载器连通性
        │     └── Checker.check_downloader()  # httpx 连接检测
        ├── RenameThread.rename_start()      # 创建 rename_loop Task
        │     └── Renamer.rename()           # module/manager
        │           └── NotificationManager  # module/notification
        ├── RSSThread.rss_start()            # 创建 rss_loop Task
        │     ├── RSSAnalyser.rss_to_data()  # module/rss
        │     └── RSSEngine.refresh_rss()    # module/rss
        │           └── DownloadClient       # module/downloader
        ├── OffsetScanThread.scan_start()    # 创建 scan_loop Task
        │     └── OffsetScanner.scan_all()   # module/core/offset_scanner
        │           ├── Database             # module/database
        │           └── tmdb_parser()        # module/parser/analyser
        ├── CalendarRefreshThread.calendar_start()  # 创建 calendar_loop Task
        │     └── TorrentManager.refresh_calendar()  # module/manager
        └── DandanplayThread.dandanplay_start()      # 创建 dandanplay_loop Task
              ├── Database.get_bangumi_missing_dandanplay()  # module/database
              └── batch_update_dandanplay_titles()         # module/searcher/dandanplay
```

### 上游调用链

```
main.py lifespan startup
  └── program.startup()    # asyncio.create_task 异步启动

main.py lifespan shutdown
  └── program.stop()

API 路由 (module/api/program.py)
  ├── GET /api/restart    -> program.restart()
  ├── GET /api/start      -> program.start()
  ├── GET /api/stop       -> program.stop()
  ├── GET /api/status     -> program.is_running / program.first_run
  ├── GET /api/shutdown   -> program.stop() + SIGINT
  └── GET /api/check/downloader -> program.check_downloader()
```

注意：`module/api/program.py` 中 `program = Program()` 创建了一个独立实例，`main.py` 中通过 `from module.api.program import program` 引用的是同一个模块级单例。

## 数据链路图

### 核心状态数据

```
ProgramStatus (基类状态)
  ├── _tasks_started: bool        # 所有任务是否已启动
  ├── _downloader_status: bool    # 下载器连通状态（带 60s TTL 缓存）
  ├── _downloader_last_check      # 上次检查时间戳
  ├── stop_event: asyncio.Event   # 全局停止信号（未实际使用）
  ├── lock: asyncio.Lock          # 全局锁（未实际使用）
  └── event: asyncio.Event        # 全局事件（未实际使用）

Program (附加状态)
  └── _startup_done: bool         # 防止 lifespan 嵌套重复启动

RSSThread
  ├── _rss_task: asyncio.Task
  └── _rss_stop_event: asyncio.Event

RenameThread
  ├── _rename_task: asyncio.Task
  └── _rename_stop_event: asyncio.Event

OffsetScanThread
  ├── _scan_task: asyncio.Task
  └── _scan_stop_event: asyncio.Event

CalendarRefreshThread
  ├── _calendar_task: asyncio.Task
  └── _calendar_stop_event: asyncio.Event

DandanplayThread
  ├── _dandanplay_task: asyncio.Task
  └── _dandanplay_stop_event: asyncio.Event
```

### DandanplayThread 数据流

```
settings.bangumi_manage.rename_method   # 配置来源：是否使用 dandanplay
settings.dandanplay.enable              # 配置来源：dandanplay 功能开关
settings.dandanplay.app_id              # 配置来源：API 凭证
settings.dandanplay.app_secret          # 配置来源：API 凭证
       │
       ▼
DandanplayThread.dandanplay_loop()
       │  每 24h 循环
       ▼
Database.get_bangumi_missing_dandanplay()  # 查询缺少 dandanplay 标题的番剧记录
       │
       ▼
batch_update_dandanplay_titles(records, app_id, app_secret)  # 批量更新标题
       │
       ▼
Database (持久化更新结果)
```

### 线程启动顺序数据流

```
start() 执行顺序：
  1. settings.load()                    # 重新加载配置到内存
  2. check_downloader_status() (循环)   # 阻塞直到下载器可用或超时
  3. rename_start()  [条件: enable_renamer]
  4. rss_start()     [条件: enable_rss]
  5. scan_start()    [无条件]
  6. calendar_start() [无条件]
  7. dandanplay_start() [无条件]
  8. _tasks_started = True
```

## 链路详情

### DandanplayThread 生命周期管理

| 阶段 | 方法 | 行为 | 资源清理 |
|------|------|------|----------|
| 初始化 | `__init__` | 创建 `_dandanplay_task=None`, `_dandanplay_stop_event=Event()` | 无 |
| 启动 | `dandanplay_start` | 清除 stop_event，创建 asyncio.Task 运行 `dandanplay_loop` | 无 |
| 运行 | `dandanplay_loop` | 120s 延迟后进入 24h 循环，条件检查配置后执行批量更新 | 每轮循环内部 try-except 吞掉异常 |
| 停止 | `dandanplay_stop` | 设置 stop_event，cancel Task，await Task，置 None | Task 被取消，CancelledError 被捕获 |

### 多重继承 super().__init__() MRO 链分析

Python C3 线性化算法对 `Program(RenameThread, RSSThread, OffsetScanThread, CalendarRefreshThread, DandanplayThread)` 的 MRO 结果：

```
Program -> DandanplayThread -> CalendarRefreshThread -> OffsetScanThread
  -> RenameThread -> RSSThread -> ProgramStatus -> Checker -> object
```

注意：MRO 中 `DandanplayThread` 排在 `RenameThread` 和 `RSSThread` 之前，但类声明中 `RenameThread` 排在前面。这是因为 C3 算法保证了**从左到右、从右到左的一致性**，右侧的基类在 MRO 中优先。这意味着 `super().__init__()` 的调用顺序是：

1. `Program.__init__` -> `super().__init__()` -> `DandanplayThread.__init__`
2. `DandanplayThread.__init__` -> `super().__init__()` -> `CalendarRefreshThread.__init__`
3. 依次类推... -> `Checker.__init__` -> `super().__init__()` -> `object.__init__`

每个基类的 `__init__` 都会创建各自的 asyncio.Event 和 Task 引用，**不存在覆盖冲突**，因为每个基类使用不同名称的属性。

### 各线程初始化延迟对比

| 线程 | 初始延迟 | 循环间隔 | 启动条件 |
|------|---------|---------|---------|
| RenameThread | 无 | settings.program.rename_time (60s) | enable_renamer |
| RSSThread | 无 | settings.program.rss_time (900s) | enable_rss |
| OffsetScanThread | 60s | 6h | 无条件 |
| CalendarRefreshThread | 120s | 24h | 无条件 |
| DandanplayThread | 120s | 24h | 无条件 |

## 问题清单

### 严重问题（8-10分）

**无**

### 一般问题（5-7分）

#### 1. ProgramStatus 中未使用的同步原语 [5分]

`ProgramStatus.__init__` 创建了 `stop_event`、`lock`、`event` 三个 asyncio 同步原语，但整个代码库中没有任何地方使用它们。这些是冗余资源。

- 位置：`module/core/status.py` 第 13-19 行
- 建议：删除未使用的 `stop_event`、`lock`、`event` 属性

#### 2. startup() 中 asyncio.create_task 的 Fire-and-Forget [6分]

`main.py` 第 40 行 `asyncio.create_task(program.startup())` 启动了 startup 但没有保存 Task 引用。如果 startup 抛出异常，该异常会被静默吞掉（Python 会在垃圾回收 Task 时打印警告）。虽然 startup 内部有 try-except 保护，但 `from_30_to_31()` 和 `from_31_to_32()` 是 await 的外部函数，异常传播路径不可控。

- 位置：`main.py` 第 40 行
- 建议：保存 Task 引用或在 lifespan 中直接 `await program.startup()`

#### 3. dandanplay_loop 中延迟导入但缺少模块级别缓存 [5分]

`dandanplay_loop` 内部每次循环都执行 `from module.database import Database` 和 `from module.searcher.dandanplay import batch_update_dandanplay_titles`。虽然 Python 会缓存已导入的模块，但这种在循环体内使用延迟导入的模式与 `RSSThread`（在文件顶部导入 DownloadClient）的风格不一致，增加了认知负担。

- 位置：`sub_thread.py` 第 230-237 行
- 建议：将导入移到文件顶部，与其他 Thread 保持一致

### 轻微问题（1-4分）

#### 1. _tasks_started 在 start() 和 stop() 之外缺乏线程安全保证 [3分]

`_tasks_started` 是普通布尔值，虽然当前所有访问都在同一事件循环内，但 `restart()` 方法中先 stop 再 start 的模式没有锁保护，理论上在 API 并发调用 restart 时可能出现竞态。

- 位置：`program.py` 第 115、131 行
- 建议：当前单事件循环模型下风险极低，可保持现状

#### 2. start() 中 scan_start/calendar_start/dandanplay_start 无条件启动 [3分]

与 `rename_start` 和 `rss_start` 有配置开关保护不同，`scan_start()`、`calendar_start()`、`dandanplay_start()` 无条件启动。虽然 dandanplay_loop 内部有条件检查，但 Task 本身仍然被创建并占用资源（至少 60-120s 的初始延迟期间）。

- 位置：`program.py` 第 110-114 行
- 建议：对 scan_start 和 calendar_start 也增加配置条件判断

#### 3. stop() 中未检查各个 Task 是否已启动 [2分]

`stop()` 直接调用 `rename_stop()`、`rss_stop()` 等方法，这些方法内部检查了 Task 是否为 None，但 `stop()` 本身没有 `_tasks_started` 的前置检查与 `start()` 对称（虽然 `is_running` 属性会检查 `_tasks_started`，但 stop 方法入口仅检查 `is_running`）。

- 位置：`program.py` 第 124-131 行
- 当前实现已经通过 `is_running` 检查间接保护，问题不严重

## 建议

### 重点关注：DandanplayThread 的继承和生命周期管理

1. **MRO 链正确性**：当前多重继承的 MRO 链正确，每个基类的属性命名空间不冲突，super().__init__() 链完整。C3 线性化结果与代码意图一致。

2. **启动顺序合理性**：先启动下载器检测 -> 再启动核心功能（rename/rss）-> 最后启动辅助功能（scan/calendar/dandanplay）。这个顺序是合理的，因为辅助功能依赖数据库和配置的稳定状态。

3. **停止顺序对称性**：stop() 中按 rename -> rss -> scan -> calendar -> dandanplay 的顺序停止，与启动顺序基本对称。各 stop 方法都正确处理了 Task 取消和异常捕获。

4. **潜在的改进**：dandanplay_loop 中的延迟导入模式虽然功能正确但风格不一致，建议统一到文件顶部导入。同时建议为 scan_start 和 calendar_start 也增加配置级别的开关控制。
