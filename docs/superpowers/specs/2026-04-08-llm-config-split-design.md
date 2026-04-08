# LLM 配置拆分设计

## 背景

当前 `ExperimentalOpenAI` 配置只有一个 `enable` 总开关，开启后所有 AI 功能（标题解析增强）全部生效，无法细粒度控制。Dandanplay 配置独立于 LLM 配置，但两者在功能上有关联（AI 增强 dandanplay 搜索）。需要将 LLM 配置拆分为"服务商配置"和"功能开关"两部分。

## 目标

1. LLM 服务商配置和功能使用配置分离，支持独立开关
2. model 字段改为自由输入（不再限定下拉选项）
3. Dandanplay 凭据合并到 LLM 配置面板（移除独立面板）
4. 支持 AI 增强 dandanplay 搜索（多关键词 + AI 筛选）
5. 最小化对现有字段的改动

## 后端配置模型

### 新增 LLMFeatures

```python
class LLMFeatures(BaseModel):
    enable_title_enhancement: bool = False   # 标题解析增强
    enable_rss_match: bool = False            # RSS 番剧识别
    enable_dandanplay_match: bool = False     # 弹弹 Play AI 匹配
```

### ExperimentalOpenAI 修改

新增 `features` 字段，所有现有字段保持不变：

```python
class ExperimentalOpenAI(BaseModel):
    enable: bool = False                              # 总开关（不变）
    api_type: Literal["azure", "openai"] = "openai"   # 不变
    api_key: str = ""                                  # 不变
    api_base: str = "https://api.openai.com/v1"       # 不变
    api_version: str = "2023-05-15"                   # 不变
    model: str = "gpt-3.5-turbo"                      # 不变
    deployment_id: str = ""                            # 不变
    features: LLMFeatures = Field(default_factory=LLMFeatures)  # 新增
```

`enable` 的语义变为"LLM 服务商连接开关"：控制是否启用任何 LLM 功能。前端在 `enable=False` 时应隐藏或禁用功能开关区域。

### DandanplayConfig

后端模型保持不变（enable + app_id + app_secret）。`dandanplay.enable` 保留，作为 dandanplay API 功能的独立开关（控制是否使用 dandanplay 进行重命名/匹配，与 LLM 无关）。前端凭据移入 LLM 面板后，`dandanplay.enable` 不再单独展示——其语义由 rename_method 隐含（选择 dandanplay 重命名方式即表示启用）。

### 配置迁移

现有用户的 `config.json` 中 `experimental_openai` 没有 `features` 字段。Pydantic 会填充默认值（全部 False），导致原有 `enable=True` 的用户升级后 AI 功能静默失效。

迁移策略：在 `_migrate_old_config()` 中检测 `experimental_openai.enable=True` 且 `features` 不存在时，自动将三个 feature 标志设为 `True`。

## 前端 UI

### config-openai.vue 改造

面板标题改为 "LLM 配置"，布局分四个区域：

1. **总开关**：启用 LLM（保留原 enable）。关闭时隐藏下方的功能开关区域
2. **服务商设置**：api_type（下拉保留）、api_key、api_base、model（改为 text input）、Azure 字段（保留）
3. **功能开关**（新增区域，仅在 enable=True 时显示）：
   - 标题解析增强 (`features.enable_title_enhancement`)
   - RSS 番剧识别 (`features.enable_rss_match`)
   - 弹弹 Play 匹配 (`features.enable_dandanplay_match`)
4. **弹弹 Play 凭据**（从独立面板移入）：app_id + app_secret

### config-dandanplay.vue

移除此组件。config.vue 中去掉 `<config-dandanplay />` 引用。

### config-manage.vue

rename_method 下拉已有 dandanplay，无需改动。

### 类型定义

- `OpenAIModel` 类型改为 `string`（自由输入）
- 新增 `LLMFeatures` 接口
- `ExperimentalOpenAI` 类型新增 `features` 字段

## 后端业务逻辑

### 触发条件变更

| 场景 | 条件 |
|------|------|
| 标题解析增强 | `enable and features.enable_title_enhancement` |
| RSS 番剧识别 | `enable and features.enable_rss_match` |
| dandanplay AI 匹配 | `enable and features.enable_dandanplay_match` |

### AIMatcher 调用点适配

现有调用点使用 `settings.experimental_openai.dict(exclude={"enable"})` 传递给 AIMatcher。新增 `features` 字段后需同步排除：

```python
kwargs = settings.experimental_openai.dict(exclude={"enable", "features"})
```

### Dandanplay 重命名决策树

```
rename_method in ("dandanplay", "subtitle_dandanplay")?
├── 否 → 原有逻辑
└── 是 → dandanplay app_id/app_secret 已配置?
    ├── 否 → 回退：使用 official_title 作为 bangumi_name
    └── 是 → dandanplay_title 已有?
        ├── 是 → 直接使用
        └── 否 → enable and features.enable_dandanplay_match?
            ├── 是 → AI 多关键词搜索 dandanplay + AI 筛选
            └── 否 → official_title 直接搜索 dandanplay
                     未命中 → 使用 official_title 作为 bangumi_name
```

"回退 normal"的含义：不改变 rename_method，而是在 dandanplay 路径中使用 official_title 作为 bangumi_name（与当前 renamer 行为一致）。

### DandanplayClient 搜索接口改造

当前 `DandanplayClient.search()` 返回 `Optional[str]`（第一个匹配的 animeTitle）。AI 增强搜索需要完整的候选列表。新增 `search_candidates()` 方法返回 `list[dict]`（包含 animeTitle、animeId、type 等字段），供 `AIMatcher.search_and_match` 使用。原 `search()` 方法保持不变，避免影响现有调用点。

### AI 增强 dandanplay 搜索流程

复用 `AIMatcher.search_and_match` 模式：

1. AI 生成 3-5 个搜索关键词（中日英罗马音变体）
2. 对每个关键词调用 `DandanplayClient.search_candidates()`
3. 收集所有候选结果，按 animeId 去重
4. AI 从候选列表中筛选最佳匹配（置信度 >= 0.7）
5. 匹配成功则更新 `dandanplay_title`

### 配置更新触发

切换到 dandanplay 重命名时，仍触发全量补全。补全策略根据 `features.enable_dandanplay_match` 决定用 AI 还是普通搜索。`dandanplay.enable` 的检查移除（由 rename_method 隐含）。

## 影响范围

### 后端文件

| 文件 | 改动 |
|------|------|
| `module/models/config.py` | 新增 LLMFeatures，ExperimentalOpenAI 加 features 字段 |
| `module/conf/config.py` | 配置迁移：旧 enable=True 用户自动开启 features |
| `module/rss/analyser.py` | 标题解析触发条件改为检查 features；AIMatcher 调用排除 features |
| `module/searcher/ai_matcher.py` | 不变 |
| `module/searcher/dandanplay.py` | 新增 search_candidates() 方法 |
| `module/manager/renamer.py` | dandanplay 重命名加凭据检查 + AI/普通搜索分支 |
| `module/api/config.py` | 全量补全策略适配 features，移除 dandanplay.enable 检查 |
| `module/core/sub_thread.py` | DandanplayThread 启动条件适配 |

### 前端文件

| 文件 | 改动 |
|------|------|
| `webui/src/components/setting/config-openai.vue` | 重构：加功能开关 + dandanplay 凭据区 |
| `webui/src/components/setting/config-dandanplay.vue` | 移除 |
| `webui/src/pages/index/config.vue` | 去掉 config-dandanplay 引用 |
| `webui/src/types/config.ts` | 新增 LLMFeatures，修改 ExperimentalOpenAI 类型 |
| `webui/src/i18n/zh-CN.json` | 新增功能开关和弹弹 Play 凭据的翻译 |
| `webui/src/i18n/en.json` | 同上 |
