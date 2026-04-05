# Scan Torrents 前端实现计划

## 概述

将集数管理弹窗（Episode Manager）从读取本地 torrent 表改为实时从 RSS 扫描种子，展示匹配详情和过滤原因，并支持按 URL 重新收集下载。

## 涉及文件

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `webui/types/bangumi.ts` | 新增 ScannedTorrent、ScanTorrentsResponse 接口 |
| 修改 | `webui/src/api/bangumi.ts` | 新增 scanTorrents()、recollectByUrls() |
| 修改 | `webui/src/i18n/zh-CN.json` | 新增扫描结果相关 i18n 键 |
| 修改 | `webui/src/components/ab-episode-manager.vue` | 重写模板和脚本，使用 scan API |

---

## Task 1: 新增 TypeScript 接口

**文件**: `webui/types/bangumi.ts`

在文件末尾（`TorrentDetail` 接口之后）添加两个新接口：

```typescript
/** 扫描种子结果，对应后端 ScannedTorrent */
export interface ScannedTorrent {
  /** 种子名称 */
  name: string
  /** 种子下载链接，用作唯一标识 */
  url: string
  /** "downloaded" = 匹配且符合下载条件；"filtered" = 匹配但被过滤 */
  download_action: 'downloaded' | 'filtered'
  /** 匹配到的模式字符串 */
  matched_pattern: string | null
  /** 匹配模式类型：title_raw 或 alias */
  pattern_type: 'title_raw' | 'alias' | null
  /** 被过滤的原因，仅 filtered 时有值 */
  filter_reason: string | null
}

/** 扫描种子响应，对应后端 ScanTorrentsResponse */
export interface ScanTorrentsResponse {
  /** 匹配报告文本，展示在弹窗底部折叠区域 */
  report: string
  /** 匹配到当前番剧的种子列表 */
  torrents: ScannedTorrent[]
}
```

**说明**:
- `ScannedTorrent` 与后端 `ScannedTorrent(BaseModel)` 一一对应
- `ScanTorrentsResponse` 与后端 `ScanTorrentsResponse(BaseModel)` 一一对应
- 不删除 `TorrentDetail`，其他地方可能仍在使用

---

## Task 2: 新增 API 客户端函数

**文件**: `webui/src/api/bangumi.ts`

### 2a. 更新 import

在文件顶部的 import 中添加新类型：

```typescript
import type {
  BangumiAPI,
  BangumiRule,
  DetectOffsetRequest,
  DetectOffsetResponse,
  OffsetSuggestion,
  ScanTorrentsResponse,    // 新增
  TorrentDetail,
} from '#/bangumi';
```

### 2b. 在 apiBangumi 对象末尾添加两个新方法

在 `recollectTorrents` 方法之后添加：

```typescript
/**
 * 实时从 RSS 扫描番剧种子，不写入数据库
 * @param bangumiId - bangumi 的 id
 * @returns 扫描结果，包含种子列表和匹配报告
 */
async scanTorrents(bangumiId: number) {
  const { data } = await axios.post<ScanTorrentsResponse>(
    `api/v1/bangumi/${bangumiId}/scan-torrents`
  );
  return data;
},

/**
 * 按种子 URL 列表提交下载（从扫描结果中选择）
 * @param bangumiId - bangumi 的 id
 * @param torrentUrls - 要下载的种子 URL 列表
 */
async recollectByUrls(bangumiId: number, torrentUrls: string[]) {
  const { data } = await axios.post<ApiSuccess>(
    `api/v1/bangumi/${bangumiId}/recollect-by-urls`,
    { torrent_urls: torrentUrls }
  );
  return data;
},
```

**说明**:
- `scanTorrents` 用 POST（后端规格要求 POST），无请求体
- `recollectByUrls` 传 `{ torrent_urls: string[] }` 作为请求体
- 保留原有的 `getTorrents` 和 `recollectTorrents` 不动，不破坏其他可能的调用方

---

## Task 3: 更新 i18n 键

**文件**: `webui/src/i18n/zh-CN.json`

将 `episode_manager` 部分替换为以下内容。新增的键包括：`scan_empty`、`action.downloaded`、`action.filtered`、`matched_pattern`、`filter_reason`、`report_title`、`report_expand`、`report_collapse`、`no_rss`。删除 `status` 子对象（旧的三种状态不再使用）。

```json
"episode_manager": {
  "title": "集数管理",
  "empty": "暂无种子记录",
  "scan_empty": "RSS 中无匹配当前番剧的种子",
  "no_rss": "未配置 RSS 链接",
  "selected_count": "已选 {selected}/{total} 项",
  "action": {
    "downloaded": "可下载",
    "filtered": "已过滤"
  },
  "matched_pattern": "匹配: {pattern}",
  "filter_reason": "原因: {reason}",
  "footer_stats": "共 {total} 条，可下载 {downloaded} 条",
  "recollect_btn": "重新收集下载 ({count})",
  "recollect_success": "成功重新收集 {count} 条",
  "recollect_failed": "重新收集失败",
  "report_title": "匹配报告",
  "report_expand": "展开报告",
  "report_collapse": "收起报告"
}
```

**变更说明**:
- `status.downloaded/downloading/not_downloaded` 替换为 `action.downloaded/filtered`，与新数据模型对齐
- 新增 `scan_empty` 用于 scan 无匹配时的空状态文案
- 新增 `no_rss` 用于 RSS 链接未配置时的提示
- 新增 `matched_pattern`、`filter_reason` 用于种子行内详情
- 新增 `report_*` 用于底部折叠报告区域
- `footer_stats` 文案调整：从"集"改为"条"，从"已下载"改为"可下载"

---

## Task 4: 重写 ab-episode-manager.vue

**文件**: `webui/src/components/ab-episode-manager.vue`

完全替换此文件。下面是完整的新文件内容。

### 设计要点

1. **数据源**: `fetchTorrents()` 调 `apiBangumi.scanTorrents()` 而非 `getTorrents()`
2. **选择模型**: `selectedUrls: Set<string>` 而非 `selectedIds: Set<number>`，URL 作为种子唯一标识
3. **种子分类**:
   - `downloaded`（download_action）: 正常样式，可勾选，可 recollect
   - `filtered`: 灰色样式，不可勾选，显示 filter_reason
4. **全选逻辑**: 只全选 downloaded 的种子（filtered 不参与）
5. **recollect**: 传 `torrent_urls` 数组（从 selectedUrls 中取）
6. **报告区域**: 底部可折叠区域展示 report 文本
7. **空状态**: 区分"无匹配种子"和"加载中"

### 完整文件内容

```vue
<script lang="ts" setup>
import { Close } from '@icon-park/vue-next'
import { NSpin, useMessage } from 'naive-ui'
import type { BangumiRule } from '#/bangumi'
import type { ScannedTorrent, ScanTorrentsResponse } from '#/bangumi'

const emit = defineEmits<{
  (e: 'close'): void
}>()

const props = defineProps<{
  bangumi: BangumiRule
}>()

const { t } = useMyI18n()
const message = useMessage()

const show = defineModel('show', { default: false })
const loading = ref(false)
const recollecting = ref(false)
const scanResult = ref<ScanTorrentsResponse | null>(null)
const selectedUrls = ref<Set<string>>(new Set())
const reportExpanded = ref(false)

watch(show, async (val) => {
  if (val) {
    await fetchTorrents()
  }
})

async function fetchTorrents() {
  loading.value = true
  scanResult.value = null
  selectedUrls.value = new Set()
  try {
    scanResult.value = await apiBangumi.scanTorrents(props.bangumi.id)
    // 默认全选 downloaded 的种子
    const newSelected = new Set<string>()
    for (const torrent of scanResult.value.torrents) {
      if (torrent.download_action === 'downloaded') {
        newSelected.add(torrent.url)
      }
    }
    selectedUrls.value = newSelected
  } finally {
    loading.value = false
  }
}

/** downloaded 种子列表 */
const downloadedTorrents = computed(() =>
  scanResult.value?.torrents.filter((t) => t.download_action === 'downloaded') ?? []
)

/** filtered 种子列表 */
const filteredTorrents = computed(() =>
  scanResult.value?.torrents.filter((t) => t.download_action === 'filtered') ?? []
)

/** 全部种子列表（downloaded 在前，filtered 在后） */
const allTorrents = computed(() => [
  ...downloadedTorrents.value,
  ...filteredTorrents.value,
])

/** 可选种子总数（仅 downloaded） */
const selectableCount = computed(() => downloadedTorrents.value.length)

const isAllSelected = computed(() => {
  if (selectableCount.value === 0) return false
  return selectedUrls.value.size === selectableCount.value
})

const selectedCount = computed(() => selectedUrls.value.size)
const totalCount = computed(() => scanResult.value?.torrents.length ?? 0)

/** 是否有任何种子 */
const hasTorrents = computed(() => (scanResult.value?.torrents.length ?? 0) > 0)

function toggleAll() {
  if (isAllSelected.value) {
    selectedUrls.value = new Set()
  } else {
    selectedUrls.value = new Set(downloadedTorrents.value.map((t) => t.url))
  }
}

function toggleItem(url: string) {
  const torrent = scanResult.value?.torrents.find((t) => t.url === url)
  // filtered 种子不可勾选
  if (!torrent || torrent.download_action === 'filtered') return

  const newSet = new Set(selectedUrls.value)
  if (newSet.has(url)) {
    newSet.delete(url)
  } else {
    newSet.add(url)
  }
  selectedUrls.value = newSet
}

function isSelected(url: string) {
  return selectedUrls.value.has(url)
}

async function recollect() {
  if (selectedUrls.value.size === 0) return
  recollecting.value = true
  try {
    await apiBangumi.recollectByUrls(
      props.bangumi.id,
      Array.from(selectedUrls.value)
    )
    message.success(
      t('episode_manager.recollect_success', {
        count: selectedUrls.value.size,
      })
    )
    show.value = false
  } catch {
    message.error(t('episode_manager.recollect_failed'))
  } finally {
    recollecting.value = false
  }
}

function close() {
  show.value = false
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="episode-backdrop" @click.self="close">
        <div class="episode-modal" role="dialog" aria-modal="true">
          <!-- Header -->
          <header class="episode-header">
            <div>
              <h2 class="episode-title">{{ $t('episode_manager.title') }}</h2>
              <p class="episode-subtitle">
                {{ bangumi.official_title }} S{{ bangumi.season }}
                <template v-if="bangumi.group_name"> · {{ bangumi.group_name }}</template>
              </p>
            </div>
            <button class="close-btn" aria-label="Close" @click="close">
              <Close theme="outline" size="18" />
            </button>
          </header>

          <!-- Content -->
          <div class="episode-content">
            <!-- Loading -->
            <div v-if="loading" class="episode-loading">
              <NSpin :size="24" />
            </div>

            <!-- Empty state: scan returned no torrents -->
            <div v-else-if="!hasTorrents" class="episode-empty">
              <p>{{ $t('episode_manager.scan_empty') }}</p>
            </div>

            <!-- Torrent list -->
            <template v-else>
              <!-- Select all bar -->
              <div class="select-bar">
                <label class="select-all" @click="toggleAll">
                  <input
                    type="checkbox"
                    :checked="isAllSelected"
                    class="checkbox"
                    @click.stop
                  />
                  <span>{{ $t('common.selectAll') }}</span>
                </label>
                <span class="select-count">
                  {{ $t('episode_manager.selected_count', { selected: selectedCount, total: totalCount }) }}
                </span>
              </div>

              <!-- Torrent rows -->
              <div class="torrent-list">
                <div
                  v-for="torrent in allTorrents"
                  :key="torrent.url"
                  class="torrent-row"
                  :class="{
                    'torrent-row--selected': isSelected(torrent.url),
                    'torrent-row--filtered': torrent.download_action === 'filtered'
                  }"
                  @click="toggleItem(torrent.url)"
                >
                  <!-- downloaded: 可勾选; filtered: 显示禁止图标 -->
                  <input
                    v-if="torrent.download_action === 'downloaded'"
                    type="checkbox"
                    :checked="isSelected(torrent.url)"
                    class="checkbox"
                    @click.stop
                  />
                  <span v-else class="filter-icon" :title="torrent.filter_reason ?? ''">&#9888;</span>

                  <div class="torrent-info">
                    <span class="torrent-name" :title="torrent.name">{{ torrent.name }}</span>
                    <!-- 匹配模式 -->
                    <span
                      v-if="torrent.matched_pattern"
                      class="torrent-detail"
                    >
                      {{ $t('episode_manager.matched_pattern', { pattern: torrent.matched_pattern }) }}
                    </span>
                    <!-- 过滤原因（仅 filtered） -->
                    <span
                      v-if="torrent.download_action === 'filtered' && torrent.filter_reason"
                      class="torrent-detail torrent-detail--reason"
                    >
                      {{ $t('episode_manager.filter_reason', { reason: torrent.filter_reason }) }}
                    </span>
                  </div>

                  <span
                    class="torrent-action"
                    :class="`torrent-action--${torrent.download_action}`"
                  >
                    {{ $t(`episode_manager.action.${torrent.download_action}`) }}
                  </span>
                </div>
              </div>

              <!-- Report section (collapsible) -->
              <div v-if="scanResult?.report" class="report-section">
                <button
                  class="report-toggle"
                  @click="reportExpanded = !reportExpanded"
                >
                  <span class="report-toggle-text">
                    {{ $t('episode_manager.report_title') }}
                  </span>
                  <span class="report-toggle-icon">
                    {{ reportExpanded ? $t('episode_manager.report_collapse') : $t('episode_manager.report_expand') }}
                  </span>
                </button>
                <div v-if="reportExpanded" class="report-content">
                  <pre>{{ scanResult.report }}</pre>
                </div>
              </div>
            </template>
          </div>

          <!-- Footer -->
          <footer v-if="!loading && hasTorrents" class="episode-footer">
            <span class="footer-stats">
              {{ $t('episode_manager.footer_stats', { total: totalCount, downloaded: selectableCount }) }}
            </span>
            <button
              class="recollect-btn"
              :disabled="selectedCount === 0 || recollecting"
              @click="recollect"
            >
              <NSpin v-if="recollecting" :size="14" />
              <span v-else>
                {{ $t('episode_manager.recollect_btn', { count: selectedCount }) }}
              </span>
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.episode-backdrop {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-overlay);
  z-index: var(--z-modal);
  padding: 16px;
}

.episode-modal {
  width: 100%;
  max-width: 480px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.episode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.episode-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
}

.episode-subtitle {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 4px 0 0;
}

.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-muted);
  transition: all var(--transition-fast);

  &:hover {
    background: var(--color-surface-hover);
    color: var(--color-text);
  }
}

.episode-content {
  flex: 1;
  overflow-y: auto;
}

.episode-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
}

.episode-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  color: var(--color-text-muted);
  font-size: 14px;
}

.select-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-hover);
}

.select-all {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.select-count {
  font-size: 12px;
  color: var(--color-text-muted);
}

.checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  flex-shrink: 0;
  cursor: pointer;
}

.torrent-list {
  overflow-y: auto;
}

.torrent-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background-color var(--transition-fast);

  &:hover {
    background: var(--color-surface-hover);
  }

  &--selected {
    background: color-mix(in srgb, var(--color-primary) 6%, transparent);
  }

  /* filtered 种子灰色样式 */
  &--filtered {
    opacity: 0.55;
    cursor: default;

    &:hover {
      background: transparent;
    }
  }
}

/* filtered 行的警告图标 */
.filter-icon {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #d97706;
  margin-top: 1px;
}

.torrent-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.torrent-name {
  font-size: 13px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 匹配模式和过滤原因 */
.torrent-detail {
  font-size: 11px;
  color: var(--color-text-muted);

  &--reason {
    color: #d97706;
  }
}

.torrent-action {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  margin-top: 1px;

  /* 可下载 */
  &--downloaded {
    background: #dcfce7;
    color: #16a34a;
  }

  /* 已过滤 */
  &--filtered {
    background: #fef3c7;
    color: #d97706;
  }
}

/* 报告折叠区域 */
.report-section {
  border-top: 1px solid var(--color-border);
}

.report-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 20px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 12px;

  &:hover {
    background: var(--color-surface-hover);
  }
}

.report-toggle-text {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.report-toggle-icon {
  color: var(--color-text-muted);
}

.report-content {
  padding: 0 20px 12px;
  max-height: 200px;
  overflow-y: auto;

  pre {
    margin: 0;
    padding: 8px 12px;
    background: var(--color-surface-hover);
    border-radius: var(--radius-sm);
    font-size: 11px;
    line-height: 1.5;
    color: var(--color-text-secondary);
    white-space: pre-wrap;
    word-break: break-all;
  }
}

.episode-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border);
}

.footer-stats {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.recollect-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 24px;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: background-color var(--transition-fast);

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 200ms ease;

  .episode-modal {
    transition: transform 200ms ease, opacity 200ms ease;
  }
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;

  .episode-modal {
    transform: scale(0.95) translateY(10px);
    opacity: 0;
  }
}
</style>
```

### 与旧版本的关键差异

| 方面 | 旧版本 | 新版本 |
|------|--------|--------|
| 数据源 | `apiBangumi.getTorrents(id)` (GET) | `apiBangumi.scanTorrents(id)` (POST) |
| 种子类型 | `TorrentDetail[]` | `ScanTorrentsResponse { torrents: ScannedTorrent[], report }` |
| 选择标识 | `Set<number>`（torrent ID） | `Set<string>`（torrent URL） |
| 全选范围 | 所有种子 | 仅 downloaded 种子 |
| 过滤种子 | 不显示 | 灰色显示，附带原因 |
| recollect | `recollectTorrents(id, number[])` | `recollectByUrls(id, string[])` |
| 报告展示 | 无 | 底部可折叠区域 |
| 默认选中 | `not_downloaded` 状态的种子 | 所有 downloaded 种子 |

---

## Task 5: 样式细节（已包含在 Task 4 中）

Task 4 的完整文件已包含所有样式变更，这里列出关键样式点：

1. **filtered 行灰化**: `.torrent-row--filtered` 使用 `opacity: 0.55` 和 `cursor: default`
2. **filtered 行禁止 hover**: 覆写 `&:hover` 为 `background: transparent`
3. **过滤原因文字**: `.torrent-detail--reason` 使用 `color: #d97706`（警告色）
4. **过滤图标**: `.filter-icon` 占据与 checkbox 相同的空间，显示警告符号
5. **报告区域**: `.report-section` 带顶部边框，`<pre>` 标签保留格式，`max-height: 200px` 可滚动
6. **种子信息改为纵向布局**: `.torrent-info` 使用 `flex-direction: column`，名称、匹配模式、过滤原因分行展示

---

## 执行顺序

1. **Task 1** (types) -- 无依赖，先做
2. **Task 2** (API) -- 依赖 Task 1 的类型定义
3. **Task 3** (i18n) -- 无依赖，可与 Task 2 并行
4. **Task 4** (组件) -- 依赖 Task 1、2、3 全部完成
5. **Task 5** (样式) -- 已包含在 Task 4 中，无需单独执行

## 测试要点

手动测试以下场景：

1. **正常流程**: 打开弹窗 -> 看到 downloaded + filtered 种子 -> 勾选 downloaded -> 点击 recollect -> 成功
2. **filtered 展示**: filtered 种子灰色、不可勾选、hover 无变化、显示过滤原因
3. **全选**: 全选只选中 downloaded 种子，filtered 不受影响
4. **报告折叠**: 展开看到报告文本，收起隐藏
5. **空状态**: scan 返回空列表时显示"RSS 中无匹配当前番剧的种子"
6. **加载中**: 打开弹窗时显示 spinner
7. **recollect 失败**: 网络错误时显示失败提示
