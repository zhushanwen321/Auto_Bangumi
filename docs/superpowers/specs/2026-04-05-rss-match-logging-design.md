# RSS 匹配日志增强设计

## 背景

当前 RSS 刷新流程中，种子匹配和过滤的决策过程没有日志记录。用户无法追踪为什么某个番剧的种子没有被下载，导致问题排查困难。

核心问题：
- `RSSEngine.refresh_rss()` 中 `match_torrent()` 的匹配过程是"静默"的
- `filter` 字段的正则匹配没有日志记录
- 无法区分"未匹配 Bangumi"和"匹配但被过滤"两种情况

## 目标

在 RSS 刷新过程中添加详细的匹配日志，记录每个种子的完整匹配链路：
- 匹配了哪个 Bangumi（通过 title_raw 还是 alias）
- 如果被过滤，具体是哪条 filter 规则
- 如果未匹配，明确标记"未匹配"

日志写入现有日志文件，不涉及数据库存储或前端展示。

## 方案：匹配结果收集器（MatchCollector）

### 架构

新增 `MatchCollector` 类，在 `refresh_rss()` 执行期间收集所有匹配结果，最后统一生成结构化报告。

### 文件结构

```
backend/src/module/rss/
├── __init__.py
├── analyser.py
├── engine.py           # 修改：集成 MatchCollector
└── match_report.py     # 新增：MatchCollector + 数据结构 + 报告生成
```

### 数据结构

```python
@dataclass
class MatchResult:
    """单个种子的匹配结果"""
    torrent_name: str
    matched_bangumi: Bangumi | None
    download_action: str          # "downloaded", "filtered", "not_matched", "not_added"
    matched_pattern: str | None   # 匹配的具体 title_raw 或 alias
    filter_reason: str | None     # 过滤原因（如果被过滤）

@dataclass
class RSSResult:
    """单个 RSS 源的处理结果"""
    rss_name: str
    rss_id: int
    total_torrents: int
    new_torrents: int
    matches: list[MatchResult]
```

### 核心类：MatchCollector

```python
class MatchCollector:
    """收集 RSS 刷新过程中的匹配结果，生成详细报告"""

    def __init__(self):
        self.rss_results: dict[int, RSSResult] = {}

    def start_rss(self, rss: RSSItem) -> None:
        """开始处理一个 RSS 源"""

    def set_torrent_counts(self, rss_id: int, total: int, new: int) -> None:
        """设置种子获取/新增计数"""

    def record_match(self, rss_id: int, result: MatchResult) -> None:
        """记录单个种子的匹配结果"""

    def finish_rss(self, rss_id: int) -> None:
        """完成处理一个 RSS 源"""

    def generate_report(self) -> str:
        """生成完整的日志报告"""
```

### 需要修改的文件

#### 1. `module/rss/engine.py`

修改 `refresh_rss()` 方法，在关键点调用 MatchCollector：

- 获取 RSS 源后：调用 `start_rss()` 和 `set_torrent_counts()`
- 每个种子匹配后：调用 `record_match()`
- RSS 源处理完成后：调用 `finish_rss()`
- 所有源处理完成后：调用 `generate_report()` 并 `logger.info()` 输出

新增 `match_torrent_with_details()` 方法，替代原有 `match_torrent()` 的调用。该方法：
- 调用 `BangumiDatabase.match_torrent_with_pattern()` 获取 Bangumi 和匹配的 pattern
- 检查 filter 规则，记录过滤原因
- 返回 `MatchResult`

#### 2. `module/database/bangumi.py`

新增 `match_torrent_with_pattern()` 方法：
- 基于现有 `match_torrent()` 逻辑
- 额外返回匹配的具体 pattern（title_raw 或 alias 名称）
- 签名：`def match_torrent_with_pattern(self, torrent_name: str) -> Optional[tuple[Bangumi, str]]`

### 日志格式

```
========== RSS 刷新报告 ==========
处理了 3 个 RSS 源

--- 源: Mikan Project ---
获取 50 个种子，其中 12 个新种子

[下载] 成功下载 (2 个):
  推しの子 (S1):
    + [Group] 推しの子 第13话 [1080p HEVC][简繁内封]
      匹配: title_raw="推しの子", passed filter

  葬送的芙莉莲 (S1):
    + [Group] 芙莉莲 第12话 [1080p HEVC][简繁内封]
      匹配: title_raw="芙莉莲", passed filter

[过滤] 匹配但被过滤 (2 个):
  推しの子 (S1):
    - [Group] 推し之子 第13话 [720p]
      匹配: alias="推し之子", filter="1080p"
      原因: 种子名称不匹配 filter 正则 /1080p/

  葬送的芙莉莲 (S1):
    - [Group] 芙莉莲 第13话 [4K]
      匹配: title_raw="芙莉莲", filter="1080p"
      原因: 种子名称不匹配 filter 正则 /1080p/

[未匹配] 未匹配任何 Bangumi (2 个):
    - [Group] 未知的动漫 第01话
      原因: 遍历 15 个 Bangumi，无匹配

    - [Group] Another Anime S01E05
      原因: 遍历 15 个 Bangumi，无匹配

[未订阅] 已匹配但未添加下载 (6 个):
  新番测试 (S1):
    x [Group] 新番测试 第01话
      原因: Bangumi 的 added=False

---
汇总: 12 个新种子 -> 2 个下载, 2 个过滤, 2 个未匹配, 6 个未订阅
=================================
```

### 日志级别

- 完整报告：`logger.info`，确保默认可见
- 单个种子匹配细节：仅在报告中体现，不单独输出 debug 日志（避免日志膨胀）

### 不做的事

- 不修改数据库结构
- 不添加前端展示
- 不修改现有的匹配逻辑（只增加日志收集）
- 不添加配置开关（始终输出详细报告）
