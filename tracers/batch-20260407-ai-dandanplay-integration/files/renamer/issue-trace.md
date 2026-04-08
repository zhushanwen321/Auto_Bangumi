# 问题链路分析报告

## 概述
- 分析文件：`backend/src/module/manager/renamer.py`
- 基于报告：`tracers/batch-20260407-ai-dandanplay-integration/files/renamer/code-trace.md`
- 分析时间：2026-04-07
- 验证问题数量：8

## 问题验证结果

### 问题 1：`_lookup_offsets()` 方法成为死代码 [P9]

#### 问题存在性：部分存在

`_lookup_offsets()` 在生产代码（`module/`）中确实没有被任何代码调用。`rename()` 方法（第 470 行）使用的是 `_batch_lookup_offsets()`。

但 code-trace 报告遗漏了一个事实：`_lookup_offsets()` 在测试文件 `test/test_renamer.py` 中有大量引用（第 664-987 行，约 10 处调用）。这些测试仍然为 `_lookup_offsets` 方法编写了完整的测试用例，说明该方法在测试层面仍有"活跃引用"。

不过从生产代码角度看，该方法确实是死代码。`_batch_lookup_offsets` 已经完全取代了它的功能，且返回类型从 `tuple[int, int]` 升级为 `RenameInfo`（包含 `dandanplay_title`），如果有人误用 `_lookup_offsets` 会丢失 `dandanplay_title` 信息。

#### 严重程度评估：7/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 6 | 仅影响维护者，不影响运行时行为 |
| 触发概率 | 3 | 不会被触发，纯死代码 |
| 后果严重性 | 5 | 误用会丢失 dandanplay_title，但当前无调用方 |
| 描述准确性 | 5 | 报告说"搜索整个代码库无调用"不准确，测试文件中有调用 |

#### 验证链路
```
生产代码搜索 _lookup_offsets:
  renamer.py:283  def _batch_lookup_offsets()  ← rename() 第 470 行调用此方法
  renamer.py:382  def _lookup_offsets()        ← 生产代码中无任何调用方

测试代码搜索 _lookup_offsets:
  test/test_renamer.py:664-987  约 10 处调用，仍有活跃测试
```

---

### 问题 2：dandanplay 和 advance 的 gen_path 分支逻辑完全重复 [P6]

#### 问题存在性：存在

验证 `gen_path()` 中各分支的返回值格式：

- `advance`（第 92-93 行）：`f"{bangumi_name} S{season}E{episode}{file_info.suffix}"`
- `dandanplay`（第 101-102 行）：`f"{bangumi_name} S{season}E{episode}{file_info.suffix}"`
- `subtitle_advance`（第 99-100 行）：`f"{bangumi_name} S{season}E{episode}.{file_info.language}{file_info.suffix}"`
- `subtitle_dandanplay`（第 103-104 行）：`f"{bangumi_name} S{season}E{episode}.{file_info.language}{file_info.suffix}"`

四组分支两两完全相同，确认重复。实际差异确实在调用方 `rename()` 第 482-483 行：当 method 为 dandanplay 时，`bangumi_name` 被替换为 `rename_info.dandanplay_title`。

#### 严重程度评估：5/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 4 | 仅影响代码可读性和维护 |
| 触发概率 | 2 | 不产生 bug，但有误导风险 |
| 后果严重性 | 3 | 新开发者可能误以为两个分支有不同行为 |
| 描述准确性 | 9 | 描述完全准确 |

#### 验证链路
```
gen_path("advance")         → "{bangumi_name} S{S}E{E}{suffix}"    [第 93 行]
gen_path("dandanplay")      → "{bangumi_name} S{S}E{E}{suffix}"    [第 102 行]  ← 完全相同

gen_path("subtitle_advance")     → "{bangumi_name} S{S}E{E}.{lang}{suffix}"  [第 100 行]
gen_path("subtitle_dandanplay")  → "{bangumi_name} S{S}E{E}.{lang}{suffix}"  [第 104 行]  ← 完全相同

差异来源:
  rename() 第 482-483 行:
    if rename_method in ("dandanplay", "subtitle_dandanplay") and rename_info.dandanplay_title:
        bangumi_name = rename_info.dandanplay_title   ← 替换 bangumi_name
```

---

### 问题 3：`season_offset` 参数传递但未生效 [P6]

#### 问题存在性：存在

验证链路：
1. `gen_path()` 签名接收 `season_offset: int = 0`（第 65 行），注释标注 "Kept for API compatibility, but no longer used"
2. 函数体内（第 66-107 行）没有任何代码引用 `season_offset` 变量
3. 季度信息直接使用 `file_info.season`（第 70 行），注释说明偏移已在文件夹名中实现

调用方传递情况：
- `rename()` 第 491 行：`"season_offset": season_offset` 放入 kwargs
- `rename_file()` 第 118 行：接收参数，第 132 行传递给 `gen_path()`
- `rename_collection()` 第 189 行：接收参数，第 204 行传递给 `gen_path()`
- `rename_subtitles()` 第 226 行：接收参数，第 243 行传递给 `gen_path()`

整条链路中 season_offset 从 rename() 一路传递到 gen_path()，但 gen_path() 完全不使用它。

#### 严重程度评估：5/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 5 | 4 个函数签名受影响 |
| 触发概率 | 2 | 不会产生运行时错误 |
| 后果严重性 | 3 | 如果有人依赖 season_offset 修改文件名中的季度号，不会生效 |
| 描述准确性 | 9 | 描述准确，包括 "season_offset 已通过文件夹名实现" 的分析 |

#### 验证链路
```
rename() [第 491 行]
  → kwargs["season_offset"] = season_offset (来自 RenameInfo)
    → rename_file(season_offset=season_offset) [第 118 行]
      → gen_path(season_offset=season_offset) [第 132 行]
        → season_offset 未被使用 [第 65 行声明，函数体内无引用]

rename() [第 491 行]
  → kwargs["season_offset"] = season_offset
    → rename_collection(season_offset=season_offset) [第 189 行]
      → gen_path(season_offset=season_offset) [第 204 行]
        → season_offset 未被使用

rename() [第 491 行]
  → kwargs["season_offset"] = season_offset
    → rename_subtitles(season_offset=season_offset) [第 226 行]
      → gen_path(season_offset=season_offset) [第 243 行]
        → season_offset 未被使用
```

---

### 问题 4：`_batch_lookup_offsets` 异常处理过于宽泛 [P5]

#### 问题存在性：存在

第 373 行 `except Exception as e` 确实捕获所有异常。catch 后的行为是：对未成功查询的 torrent 回退到 `RenameInfo(0, 0, None)`（第 376-378 行），并以 debug 级别记录日志（第 374 行）。

数据库连接失败、SQL 语法错误等严重问题都会被吞掉，所有 torrent 的偏移量被静默重置为 0。

#### 严重程度评估：5/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 7 | 数据库故障影响所有 torrent |
| 触发概率 | 3 | 数据库故障概率较低 |
| 后果严重性 | 6 | 静默重置偏移量可能导致错误重命名 |
| 描述准确性 | 8 | 描述准确 |

#### 验证链路
```
_batch_lookup_offsets() [第 294-380 行]
  try:
    with Database() as db: ...  [第 295 行]
  except Exception as e:         [第 373 行]  ← 捕获所有异常
    logger.debug(...)            [第 374 行]  ← debug 级别，生产环境通常不可见
    for info in torrents_info:
      result[info["hash"]] = RenameInfo(0, 0, None)  [第 378 行]  ← 静默回退
```

---

### 问题 5：`gen_path` 中 episode_offset 计算逻辑与 `rename_file` 重复 [P4]

#### 问题存在性：存在

`gen_path()` 第 74-83 行和 `rename_file()` 第 156-163 行包含完全相同的逻辑：
1. EP0 不偏移（`original_episode == 0 and episode_offset != 0` → 保持 0）
2. 负值回退（`adjusted_episode < 0` → 恢复原值）
3. 零值回退（`adjusted_episode == 0 and original_episode > 0` → 恢复原值）

两处代码独立维护，存在不一致风险。

#### 严重程度评估：4/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 3 | 两处重复 |
| 触发概率 | 2 | 当前一致，但修改时可能遗漏 |
| 后果严重性 | 3 | 不一致会导致 gen_path 生成的文件名与通知中的集号不匹配 |
| 描述准确性 | 9 | 描述准确 |

#### 验证链路
```
gen_path() [第 74-83 行]:
  if original_episode == 0 and episode_offset != 0: adjusted_episode = 0
  else: adjusted_episode = original_episode + episode_offset
  if adjusted_episode < 0 or (adjusted_episode == 0 and original_episode > 0):
    adjusted_episode = original_episode

rename_file() [第 156-163 行]:
  if original_ep == 0 and episode_offset != 0: adjusted_episode = 0
  else: adjusted_episode = original_ep + episode_offset
  if adjusted_episode < 0 or (adjusted_episode == 0 and original_ep > 0):
    adjusted_episode = original_ep
```

---

### 问题 6：`rename_collection` 缺少 pending renames 防抖 [P3]

#### 问题存在性：存在

`rename_file()` 有完整的 `_pending_renames` 防抖机制（第 137-174 行），包括检查、添加、移除和定期清理。`rename_collection()`（第 181-215 行）直接调用 `rename_torrent_file()` 而没有使用防抖机制。`rename_subtitles()`（第 217-254 行）同样没有。

#### 严重程度评估：3/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 3 | 仅影响多文件集合和字幕 |
| 触发概率 | 4 | 重命名失败时会产生重复请求 |
| 后果严重性 | 2 | qBittorrent API 返回 200 但未实际重命名的场景下会产生冗余请求 |
| 描述准确性 | 8 | 描述准确 |

#### 验证链路
```
rename_file() [第 137-174 行]:
  → pending_key = (_hash, media_path, new_path)
  → 检查 _pending_renames 缓存 [第 138-146 行]
  → 成功: _pending_renames.pop() [第 152 行]
  → 失败: _pending_renames[key] = time.time() [第 172 行]

rename_collection() [第 207-211 行]:
  → await self.rename_torrent_file(...)  ← 直接调用，无防抖

rename_subtitles() [第 247-254 行]:
  → await self.rename_torrent_file(...)  ← 直接调用，无防抖
```

---

### 问题 7：`rename_subtitles` 的 verify=False 缺少重试机制 [P2]

#### 问题存在性：存在

字幕重命名时使用 `verify=False`（第 251 行），失败时仅打印 warning（第 254 行），没有像 `rename_file` 那样加入 pending cache 或重试机制。

#### 严重程度评估：2/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 2 | 仅影响字幕文件 |
| 触发概率 | 3 | 字幕重命名失败概率较低 |
| 后果严重性 | 2 | 字幕命名不正确但不影响播放 |
| 描述准确性 | 8 | 描述准确 |

#### 验证链路
```
rename_subtitles() [第 247-254 行]:
  renamed = await self.rename_torrent_file(verify=False)
  if not renamed:
    logger.warning(...)  ← 仅打印警告，无重试
```

---

### 问题 8：`dandanplay_title` 为 None 时 dandanplay 方法退化为 advance [P2]

#### 问题存在性：存在

`rename()` 第 482 行检查 `rename_info.dandanplay_title` 是否为 truthy。当为 None 时，`bangumi_name` 保持从 `_path_to_bangumi()` 获取的值，最终 gen_path 输出与 advance 方法完全一致。

#### 严重程度评估：2/10

| 评估维度 | 得分 | 说明 |
|---------|-----|------|
| 影响范围 | 3 | 影响选择 dandanplay 方法的用户 |
| 触发概率 | 4 | dandanplay API 未匹配或未配置时触发 |
| 后果严重性 | 2 | 退化为 advance 是合理的 fallback 行为 |
| 描述准确性 | 8 | 描述准确 |

#### 验证链路
```
rename() [第 482-483 行]:
  if rename_method in ("dandanplay", "subtitle_dandanplay") and rename_info.dandanplay_title:
    bangumi_name = rename_info.dandanplay_title  ← 仅当 title 非 None 时替换
  # 否则 bangumi_name 保持原值（来自 _path_to_bangumi）

gen_path("dandanplay", bangumi_name) → 与 gen_path("advance", bangumi_name) 完全相同
```

---

## 总结

| 问题 | 报告评分 | 验证评分 | 评级 |
|-----|---------|---------|------|
| `_lookup_offsets()` 死代码 | 9 | 7 | 部分存在（测试中仍有引用） |
| dandanplay/advance gen_path 分支重复 | 6 | 5 | 存在 |
| `season_offset` 参数未生效 | 6 | 5 | 存在 |
| `_batch_lookup_offsets` 异常处理过宽 | 5 | 5 | 存在 |
| episode_offset 计算逻辑重复 | 4 | 4 | 存在 |
| `rename_collection` 缺少防抖 | 3 | 3 | 存在 |
| `rename_subtitles` 缺少重试 | 2 | 2 | 存在 |
| dandanplay_title None 时退化 | 2 | 2 | 存在 |

### 统计
- 真实严重问题（8-10分）：0 个
- 部分存在问题（5-7分）：4 个
- 轻微问题（1-4分）：4 个
- 虚假问题：0 个

### 额外发现

code-trace 报告对 `_lookup_offsets` 的描述存在一处不准确：报告称"搜索整个代码库，`_lookup_offsets` 没有被任何其他代码调用"，但测试文件 `test/test_renamer.py` 中仍有约 10 处对该方法的直接调用。这意味着删除 `_lookup_offsets` 时需要同步清理测试代码。其余 7 个问题的描述均准确。
