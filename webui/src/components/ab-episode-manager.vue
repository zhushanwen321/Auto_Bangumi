<script lang="ts" setup>
import { Close } from '@icon-park/vue-next'
import { NSpin, useMessage } from 'naive-ui'
import type { BangumiRule } from '#/bangumi'
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

watch(show, async (val) => {
  if (val) {
    await fetchTorrents()
  }
})

async function fetchTorrents() {
  loading.value = true
  try {
    torrents.value = await apiBangumi.getTorrents(props.bangumi.id)
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
