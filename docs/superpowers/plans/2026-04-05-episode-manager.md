# 集数管理功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为番剧订阅系统添加"集数管理"能力，允许用户查看和重新下载缺失的剧集种子。**Architecture:** 緻加两个后端 API 知识点（获取种子列表 + 重新收集下载），和对应的前端弹框组件。后端通过数据库查询种子记录并结合 qBittorrent 实时状态返回三态信息。前端在编辑弹框中添加入口按钮，打开独立的集数管理 Modal。**Tech Stack:** Python FastAPI + SQLModel + Vue 3 + TypeScript + Vant UI

---

### Task 1: 后端 - 新增数据库查询方法

**Files:**
- Modify: `backend/src/module/database/torrent.py:49-104`
- Test: `backend/src/test/test_database.py`

- [ ] **Step 1: 写 `search_by_bangumi_id` 方法的测试**

在 `backend/src/test/test_database.py` 末尾添加:

```python
# --- TorrentDatabase search_by_bangumi_id ---


def test_torrent_search_by_bangumi_id(db_session):
    """Test searching torrents by bangumi_id."""
    db = TorrentDatabase(db_session)
    t1 = Torrent(name="Test 1", url="https://example.com/1", bangumi_id=1)
    t2 = Torrent(name="Test 2", url="https://example.com/2", bangumi_id=1)
    t3 = Torrent(name="Test 3", url="https://example.com/3", bangumi_id=2)
    db.add_all([t1, t2, t3])

    result = db.search_by_bangumi_id(1)
    assert len(result) == 2
    assert all(t.bangumi_id == 1 for t in result)


def test_torrent_search_by_bangumi_id_empty(db_session):
    """Test searching by non-existent bangumi_id returns empty list."""
    db = TorrentDatabase(db_session)
    result = db.search_by_bangumi_id(999)
    assert result == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && uv run pytest src/test/test_database.py::test_torrent_search_by_bangumi_id -v`
Expected: FAIL - `AttributeError: 'TorrentDatabase' object has no attribute 'search_by_bangumi_id'`

- [ ] **Step 3: 实现 `search_by_bangumi_id` 方法**

在 `backend/src/module/database/torrent.py` 的 `TorrentDatabase` 类中， `search_by_qb_hashes` 方法之后添加:

```python
    def search_by_bangumi_id(self, bangumi_id: int) -> list[Torrent]:
        """Find all torrents associated with a bangumi."""
        result = self.session.execute(
            select(Torrent).where(Torrent.bangumi_id == bangumi_id)
        )
        return list(result.scalars().all())
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd backend && uv run pytest src/test/test_database.py::test_torrent_search_by_bangumi_id -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/src/module/database/torrent.py backend/src/test/test_database.py
git commit -m "feat(db): add search_by_bangumi_id method to TorrentDatabase"
```

---

### Task 2: 后端 - 新增 Pydantic 模型

**Files:**
- Modify: `backend/src/module/models/torrent.py`

- [ ] **Step 1: 新增 `TorrentDetail` 和 `RecollectRequest` 模型**

在 `backend/src/module/models/torrent.py` 文件末尾添加:

```python
class TorrentDetail(BaseModel):
    """Torrent with combined download status from DB + qBittorrent."""
    id: int
    name: str
    url: str
    downloaded: bool
    status: str  # "downloaded" | "downloading" | "not_downloaded"


class RecollectRequest(BaseModel):
    """Request body for recollecting torrents."""
    torrent_ids: list[int]
```

- [ ] **Step 2: 提交**

```bash
git add backend/src/module/models/torrent.py
git commit -m "feat(models): add TorrentDetail and RecollectRequest models"
```

---

### Task 3: 后端 - 新增 API 知识点

**Files:**
- Modify: `backend/src/module/api/bangumi.py`

- [ ] **Step 1: 新增获取种子列表端点**

在 `backend/src/module/api/bangumi.py` 中:

1. 在顶部 import 区添加 `TorrentDetail` 和 `RecollectRequest`:
```python
from module.models import APIResponse, Bangumi, BangumiUpdate, TorrentDetail, RecollectRequest
 Torrent
from module.downloader import DownloadClient
 DownloadClient
```

2. 在 `set_weekday` 端点之后添加:

```python
@router.get(
    path="/{bangumi_id}/torrents",
    response_model=list[TorrentDetail],
    dependencies=[Depends(get_current_user)],
)
async def get_bangumi_torrents(bangumi_id: int):
  """Get all torrents for a bangumi with download status."""
    with Database() as db:
        torrents = db.torrent.search_by_bangumi_id(bangumi_id)
        if not torrents:
            return []

        # Collect qb_hashes for non-empty
 qb_hashes = {t.qb_hash for t in torrents if t.qb_hash}

        # Query qBittorrent for real-time status
 qb_status_map: dict[str, str] = {}
        if qb_hashes:
            try:
                async with DownloadClient() as client:
                    qb_torrents = await client.get_torrent_info(status_filter="all", category="Bangumi")
                for t in qb_torrents:
                    if t.get("hash") in qb_hashes:
                        qb_status_map[t["hash"]] = t.get("state", "")
            except Exception:
                logger.warning("[API] Failed to query qBittorrent status: %s", e)

        # Build response
        downloading_states = {"uploading", "downloading", "stalledDL"}
        result = []
        for t in torrents:
            if t.downloaded:
                status = "downloaded"
            elif t.qb_hash and t.qb_hash in qb_status_map:
                if qb_status_map[t.qb_hash] in downloading_states:
                    status = "downloading"
                else:
                    status = "not_downloaded"
            else:
                status = "not_downloaded"
            result.append(TorrentDetail(
                id=t.id,
                name=t.name,
                url=t.url,
                downloaded=t.downloaded,
                status=status,
            ))
        return result
 def get_bangumi_torrents

 get_bangumi_torrents(bangumi_id: int): ...
```

- [ ] **Step 2: 新增重新收集下载端点**

在同一个文件中继续添加:

```python
 @router.post(
    path="/{bangumi_id}/recollect",
    response_model=APIResponse,
    dependencies=[Depends(get_current_user)],
)
async def recollect_torrents(bangumi_id: int, request: RecollectRequest):
  """Re-download selected torrents for a bangumi."""
    with Database() as db:
        # Validate all torrents belong to this bangumi
        torrents = []
        for tid in request.torrent_ids:
            t = db.torrent.search(tid)
            if t is None:
                return JSONResponse(
                    status_code=404,
                    content={
                        "status": False,
                        "msg_en": f"Torrent {tid} not found.",
                        "msg_zh": f"种子 {tid} 不存在。",
                    },
                )
            if t.bangumi_id != bangumi_id:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": False,
                        "msg_en": "Torrent IDs do not belong to this bangumi.",
                        "msg_zh": "种子 ID 不属于此番剧。",
                        "mismatched_ids": [
                            tid for tid in request.torrent_ids
 if db.torrent.search(tid) and db.torrent.search(tid).bangumi_id != bangumi_id
 },
                        ],
                    },
                )
            torrents.append(t)

        if not torrents:
            return JSONResponse(
                status_code=400,
                content={
                    "status": False,
                    "msg_en": "No valid torrents to recollect.",
                    "msg_zh": "没有有效的种子可重新收集。",
                },
            )

        # Get bangumi for save path config
        bangumi = db.bangumi.search_id(bangumi_id)
        if not bangumi:
            return JSONResponse(
                status_code=404,
                content={
                    "status": False,
                    "msg_en": f"Bangumi {bangumi_id} not found.",
                    "msg_zh": f"未找到番剧 {bangumi_id}。",
                },
            )

    # Add torrents to download client
    try:
        async with DownloadClient() as client:
            success = await client.add_torrent(torrents, bangumi)
            if not success:
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": False,
                        "msg_en": "Failed to add torrents to download client.",
                        "msg_zh": "添加种子到下载客户端失败。",
                    },
                )

            # Update torrent records
 for t in torrents:
                t.downloaded = True
            db.torrent.update_all(torrents)

    except Exception as e:
        logger.error("[API] Recollect failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "status": False,
                "msg_en": f"Recollect failed: {str(e)}",
                "msg_zh": f"重新收集失败: {str(e)}",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": True,
            "msg_en": f"Successfully recollected {len(torrents)} torrents.",
            "msg_zh": f"成功重新收集 {len(torrents)} 个种子。",
        },
    )
```

- [ ] **Step 3: 提交**

```bash
git add backend/src/module/api/bangumi.py
git commit -m "feat(api): add torrents and recollect endpoints for bangumi"
```

---

### Task 4: 前端 - 新增 API 函数

**Files:**
- Modify: `webui/src/api/bangumi.ts`
- Modify: `webui/src/types/bangumi.ts`

- [ ] **Step 1: 新增 `TorrentDetail` 类型**

在 `webui/src/types/bangumi.ts` 文件末尾添加:

```typescript
export interface TorrentDetail {
  id: number
  name: string
  url: string
  downloaded: boolean
  status: 'downloaded' | 'downloading' | 'not_downloaded'
}
```

- [ ] **Step 2: 新增 API 函数**

在 `webui/src/api/bangumi.ts` 的 `apiBangumi` 对象末尾添加:

```typescript
  /**
   * 获取番剧种子列表
 - @param bangumiId - bangumi 的 id
   */
  async getTorrents(bangumiId: number) {
    const { data } = await axios.get<TorrentDetail[]>(
      `api/v1/bangumi/${bangumiId}/torrents`
    );
    return data;
  },

  /**
   * 重新收集下载选中的种子
   * @param bangumiId - bangumi 的 id
   * @param torrentIds - 要重新下载的种子 ID 列表
   */
  async recollectTorrents(bangumiId: number, torrentIds: number[]) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/bangumi/${bangumiId}/recollect`,
      { torrent_ids: torrentIds }
    );
    return data;
  },
```

- [ ] **Step 3: 提交**

```bash
git add webui/src/api/bangumi.ts webui/src/types/bangumi.ts
git commit -m "feat(frontend): add torrent API functions and TorrentDetail type"
```

---

### Task 5: 前端 - 新增集数管理弹框组件

**Files:**
- Create: `webui/src/components/ab-episode-manager.vue`

- [ ] **Step 1: 创建集数管理弹框组件**

创建 `webui/src/components/ab-episode-manager.vue`:

```vue
<script lang="ts" setup>
import { Close } from '@icon-park/vue-next'
import { NSpin, useMessage } from 'naive-ui'
import type { BangumiRule, from '#/bangumi'
import type { TorrentDetail } from '#/bangumi'

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
const torrents = ref<TorrentDetail[]>([])
const selectedIds = ref<Set<number>>(new Set())

// Fetch torrents on open
watch(show, async (val) => {
  if (val) {
    await fetchTorrents()
  }
})

async function fetchTorrents() {
  loading.value = true
  try {
    torrents.value = await apiBangumi.getTorrents(props.bangumi.id)
    // Default select all not_downloaded items
    const newSelected = new Set<number>()
    for (const t of torrents.value) {
      if (t.status === 'not_downloaded') {
        newSelected.add(t.id)
      }
    }
    selectedIds.value = newSelected
  } finally {
    loading.value = false
  }
}

const isAllSelected = computed(() => {
  if (torrents.value.length === 0) return false
  return selectedIds.value.size === torrents.value.length
})

const selectedCount = computed(() => selectedIds.value.size)

const totalCount = computed(() => torrents.value.length)

const downloadedCount = computed(
  () => torrents.value.filter((t) => t.status === 'downloaded').length
)

function toggleAll() {
  if (isAllSelected.value) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(torrents.value.map((t) => t.id))
  }
}

function toggleItem(id: number) {
  const newSet = new Set(selectedIds.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  selectedIds.value = newSet
}

function isSelected(id: number) {
  return selectedIds.value.has(id)
}

async function recollect() {
  if (selectedIds.value.size === 0) return
  recollecting.value = true
  try {
    await apiBangumi.recollectTorrents(
      props.bangumi.id,
      Array.from(selectedIds.value)
    )
    message.success(
      t('episode_manager.recollect_success', {
        count: selectedIds.value.size,
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

            <!-- Empty state -->
            <div v-else-if="torrents.length === 0" class="episode-empty">
              <p>{{ $t('episode_manager.empty') }}</p>
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
                  v-for="torrent in torrents"
                  :key="torrent.id"
                  class="torrent-row"
                  :class="{ 'torrent-row--selected': isSelected(torrent.id) }"
                  @click="toggleItem(torrent.id)"
                >
                  <input
                    type="checkbox"
                    :checked="isSelected(torrent.id)"
                    class="checkbox"
                    @click.stop
                  />
                  <span class="torrent-name" :title="torrent.name">{{ torrent.name }}</span>
                  <span
                    class="torrent-status"
                    :class="`torrent-status--${torrent.status}`"
                  >
                    {{ $t(`episode_manager.status.${torrent.status}`) }}
                  </span>
                </div>
              </div>
            </template>
          </div>

          <!-- Footer -->
          <footer v-if="!loading && torrents.length > 0" class="episode-footer">
            <span class="footer-stats">
              {{ $t('episode_manager.footer_stats', { total: totalCount, downloaded: downloadedCount }) }}
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
  align-items: center;
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
}

.torrent-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.torrent-status {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;

  &--downloaded {
    background: #dcfce7;
    color: #16a34a;
  }

  &--downloading {
    background: #dbeafe;
    color: #2563eb;
  }

  &--not_downloaded {
    background: #fef3c7;
    color: #d97706;
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

// Modal transition
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

- [ ] **Step 2: 提交**

```bash
git add webui/src/components/ab-episode-manager.vue
git commit -m "feat(frontend): add episode manager modal component"
```

---

### Task 6: 前端 - 集成到编辑弹框

**Files:**
- Modify: `webui/src/components/ab-edit-rule.vue:368-400`
footer区域)
- Modify: `webui/src/store/bangumi.ts`



 - [ ] **Step 1: 在 store 中添加集数管理状态**

在 `webui/src/store/bangumi.ts` 的 `editRule` reactive 之后添加:

```typescript
  const episodeManager = reactive<{
    show: boolean;
    item: BangumiRule;
  }>({
    show: false,
    item: { ...ruleTemplate },
  });
```

在 store 的 return 对象中添加 `episodeManager` 和 `openEpisodeManager`:

```typescript
  function openEpisodeManager(data: BangumiRule) {
    editRule.show = false  // Close edit popup first
    episodeManager.show = true;
    episodeManager.item = data;
  }
```

暴露: 在 return 中添加 `episodeManager`, `openEpisodeManager`

- [ ] **Step 2: 在编辑弹框中添加按钮和弹框引用**

在 `webui/src/components/ab-edit-rule.vue` 中:

1. 添加 import:
```vue
import AbEpisodeManager from './ab-episode-manager.vue'
```

2. 在 `footer-left` 的 div 中,归档/取消归档按钮之后、删除按钮之前添加:
```vue
              <ab-button
                size="small"
                @click="emitEpisodeManager"
              >
                {{ $t('episode_manager.title') }}
              </ab-button>
```

3. 添加 emit 和方法:
```typescript
const emit = defineEmits<{
  (e: 'apply', rule: BangumiRule): void;
  (e: 'enable', id: number): void;
  (e: 'archive', id: number): void;
  (e: 'unarchive', id: number): void;
  (e: 'episodeManager', rule: BangumiRule): void;  // 新增
  // ...existing emits
}>()

// 新增方法
function emitEpisodeManager() {
  emit('episodeManager', rule.value);
}
```

4. 在模板末尾（编辑弹框的关闭标签之前）添加:
```vue
  <!-- Episode Manager Modal -->
  <AbEpisodeManager
    v-model:show="episodeManager.show"
    :bangumi="episodeManager.item"
  />
```

5. 将 `episodeManager` 从 store 解入组件:
```typescript
const { bangumi, showArchived, isLoading, hasLoaded, activeBangumi, archivedBangumi, editRule, episodeManager } = storeToRefs(useBangumiStore());
const { openEpisodeManager } = useBangumiStore();
```

- [ ] **Step 3: 提交**

```bash
git add webui/src/components/ab-edit-rule.vue webui/src/store/bangumi.ts
git commit -m "feat(frontend): integrate episode manager into edit rule popup"
```

---

### Task 7: 前端 - 添加 i18n 籉译

**Files:**
- Modify: `webui/src/i18n/en.json`
- Modify: `webui/src/i18n/zh-CN.json`

- [ ] **Step 1: 添加英文翻译**

在 `webui/src/i18n/en.json` 中添加 `episode_manager` 键（在 `homepage` 键之前或之后）:

```json
  "episode_manager": {
    "title": "Episode Manager",
    "empty": "No torrent records found",
    "selected_count": "{selected}/{total} selected",
    "status": {
      "downloaded": "Downloaded",
      "downloading": "Downloading",
      "not_downloaded": "Not Downloaded"
    },
    "footer_stats": "{total} episodes, {downloaded} downloaded",
    "recollect_btn": "Recollect ({count})",
    "recollect_success": "Successfully recollected {count} episode(s)",
    "recollect_failed": "Failed to recollect episodes"
  },
```

- [ ] **Step 2: 添加中文翻译**

在 `webui/src/i18n/zh-CN.json` 中对应位置添加:

```json
  "episode_manager": {
    "title": "集数管理",
    "empty": "暂无种子记录",
    "selected_count": "已选 {selected}/{total} 项",
    "status": {
      "downloaded": "已下载",
      "downloading": "下载中",
      "not_downloaded": "未下载"
    },
    "footer_stats": "共 {total} 集，已下载 {downloaded} 集",
    "recollect_btn": "重新收集下载 ({count})",
    "recollect_success": "成功重新收集 {count} 集",
    "recollect_failed": "重新收集失败"
  },
```

- [ ] **Step 3: 提交**

```bash
git add webui/src/i18n/en.json webui/src/i18n/zh-CN.json
git commit -m "feat(i18n): add episode manager translations"
```

---

### Task 8: 集成测试

**Files:**
- Test: `backend/src/test/test_api_bangumi.py` (如果存在) 或创建新测试文件

- [ ] **Step 1: 为新端点编写 API 测试**

在已有的 bangumi API 测试文件中（或在 `backend/src/test/` 下新建 `test_api_episode_manager.py`）添加:

```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from module.api import v1
from module.security.api import get_current_user
from module.models import Torrent


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(v1, prefix="/api")
    return app


@pytest.fixture
def authed_client(app):
    async def mock_user():
        return "testuser"
    app.dependency_overrides[get_current_user] = mock_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestGetBangumiTorrents:
    @patch("module.api.bangumi.Database")
    @patch("module.api.bangumi.DownloadClient")
    def test_get_torrents_empty(self, mock_client, authed_client):
        """GET /bangumi/{id}/torrents returns empty list when no torrents."""
        mock_db = MagicMock()
        mock_db.torrent.search_by_bangumi_id.return_value = []
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.get_torrent_info = AsyncMock(return_value=[])

        with patch("module.api.bangumi.Database", return_value=mock_db):
            resp = authed_client.get("/api/v1/bangumi/1/torrents")
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("module.api.bangumi.DownloadClient")
    def test_get_torrents_with_status(self, mock_client, authed_client):
        """GET /bangumi/{id}/torrents maps status correctly."""
        mock_db = MagicMock()
        t1 = Torrent(id=1, name="EP01", url="http://a", bangumi_id=1, downloaded=True)
        t2 = Torrent(id=2, name="EP02", url="http://b", bangumi_id=1, downloaded=False, qb_hash="hash2")
        t3 = Torrent(id=3, name="EP03", url="http://c", bangumi_id=1, downloaded=False)
        mock_db.torrent.search_by_bangumi_id.return_value = [t1, t2, t3]

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.get_torrent_info = AsyncMock(return_value=[
            {"hash": "hash2", "state": "downloading"}
        ])

        with patch("module.api.bangumi.Database", return_value=mock_db):
            resp = authed_client.get("/api/v1/bangumi/1/torrents")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert data[0]["status"] == "downloaded"
        assert data[1]["status"] == "downloading"
        assert data[2]["status"] == "not_downloaded"
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && uv run pytest src/test/test_api_episode_manager.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add backend/src/test/test_api_episode_manager.py
git commit -m "test(api): add tests for episode manager endpoints"
```

---

### Task 9: 手动验证

- [ ] **Step 1: 启动后端服务**

Run: `cd backend/src && uv run python main.py`

- [ ] **Step 2: 启动前端开发服务**

Run: `cd webui && pnpm dev`

- [ ] **Step 3: 在浏览器中验证**

1. 打开一个已订阅的番剧编辑弹框
2. 确认 footer 区域出现「集数管理」按钮
3. 点击按钮，确认弹框打开并加载种子列表
4. 验证默认选中未下载项
5. 点击重新收集，确认 API 调用成功

- [ ] **Step 4: 最终提交**

如果需要修复问题，进行修复并提交。否则标记验证通过。
