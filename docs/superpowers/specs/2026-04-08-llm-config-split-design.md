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

### DandanplayConfig

后端模型保持不变（enable + app_id + app_secret），前端移除独立面板，凭据显示在 LLM 面板内。

## 前端 UI

### config-openai.vue 改造

面板标题改为 "LLM 配置"，布局分四个区域：

1. **总开关**：启用 LLM（保留原 enable）
2. **服务商设置**：api_type（下拉保留）、api_key、api_base、model（改为 text input）、Azure 字段（保留）
3. **功能开关**（新增区域）：
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

### Dandanplay 重命名决策树

```
rename_method in ("dandanplay", "subtitle_dandanplay")?
├── 否 → 原有逻辑
└── 是 → dandanplay_title 已有?
    ├── 是 → 直接使用
    └── 否 → features.enable_dandanplay_match?
        ├── 是 → AI 多关键词搜索 dandanplay + AI 筛选
        └── 否 → official_title 直接搜索 dandanplay
                 未命中 → 回退 normal
```

### AI 增强 dandanplay 搜索流程

复用 `AIMatcher.search_and_match` 模式：

1. AI 生成 3-5 个搜索关键词（中日英罗马音变体）
2. 对每个关键词调用 `DandanplayClient.search()`
3. AI 从候选列表中筛选最佳匹配（置信度 >= 0.7）
4. 匹配成功则更新 `dandanplay_title`

### 配置更新触发

切换到 dandanplay 重命名时，仍触发全量补全。补全策略根据 `features.enable_dandanplay_match` 决定用 AI 还是普通搜索。

## 影响范围

### 后端文件

| 文件 | 改动 |
|------|------|
| `module/models/config.py` | 新增 LLMFeatures，ExperimentalOpenAI 加 features 字段 |
| `module/rss/analyser.py` | 标题解析触发条件改为检查 features |
| `module/searcher/ai_matcher.py` | 不变 |
| `module/searcher/dandanplay.py` | 新增 AI 增强 dandanplay 搜索函数 |
| `module/manager/renamer.py` | dandanplay 重命名加 AI/普通搜索分支 |
| `module/api/config.py` | 全量补全策略适配 features |

### 前端文件

| 文件 | 改动 |
|------|------|
| `components/setting/config-openai.vue` | 重构：加功能开关 + dandanplay 凭据区 |
| `components/setting/config-dandanplay.vue` | 移除 |
| `pages/index/config.vue` | 去掉 config-dandanplay 引用 |
| `types/config.ts` | 新增 LLMFeatures，修改 ExperimentalOpenAI 类型 |
| `i18n/zh-CN.json` | 新增功能开关和弹弹 Play 凭据的翻译 |
| `i18n/en.json` | 同上 |
