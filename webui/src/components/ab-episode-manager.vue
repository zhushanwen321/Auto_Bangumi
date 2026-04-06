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

const downloadedTorrents = computed(() =>
  scanResult.value?.torrents.filter((t) => t.download_action === 'downloaded') ?? []
)

const filteredTorrents = computed(() =>
  scanResult.value?.torrents.filter((t) => t.download_action === 'filtered') ?? []
)

const allTorrents = computed(() => [
  ...downloadedTorrents.value,
  ...filteredTorrents.value,
])

const selectableCount = computed(() => downloadedTorrents.value.length)

const isAllSelected = computed(() => {
  if (selectableCount.value === 0) return false
  return selectedUrls.value.size === selectableCount.value
})

const selectedCount = computed(() => selectedUrls.value.size)
const totalCount = computed(() => scanResult.value?.torrents.length ?? 0)
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

          <div class="episode-content">
            <div v-if="loading" class="episode-loading">
              <NSpin :size="24" />
            </div>

            <div v-else-if="!hasTorrents" class="episode-empty">
              <p>{{ $t('episode_manager.scan_empty') }}</p>
            </div>

            <template v-else>
              <div class="select-bar">
                <label class="select-all" @click="toggleAll">
                  <input type="checkbox" :checked="isAllSelected" class="checkbox" @click.stop />
                  <span>{{ $t('common.selectAll') }}</span>
                </label>
                <span class="select-count">
                  {{ $t('episode_manager.selected_count', { selected: selectedCount, total: totalCount }) }}
                </span>
              </div>

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
                    <span v-if="torrent.matched_pattern" class="torrent-detail">
                      {{ $t('episode_manager.matched_pattern', { pattern: torrent.matched_pattern }) }}
                    </span>
                    <span
                      v-if="torrent.download_action === 'filtered' && torrent.filter_reason"
                      class="torrent-detail torrent-detail--reason"
                    >
                      {{ $t('episode_manager.filter_reason', { reason: torrent.filter_reason }) }}
                    </span>
                  </div>

                  <span class="torrent-action" :class="`torrent-action--${torrent.download_action}`">
                    {{ $t(`episode_manager.action.${torrent.download_action}`) }}
                  </span>
                </div>
              </div>

              <div v-if="scanResult?.report" class="report-section">
                <button class="report-toggle" @click="reportExpanded = !reportExpanded">
                  <span class="report-toggle-text">{{ $t('episode_manager.report_title') }}</span>
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
              <span v-else>{{ $t('episode_manager.recollect_btn', { count: selectedCount }) }}</span>
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

  &--filtered {
    opacity: 0.55;
    cursor: default;

    &:hover {
      background: transparent;
    }
  }
}

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

  &--downloaded {
    background: #dcfce7;
    color: #16a34a;
  }

  &--filtered {
    background: #fef3c7;
    color: #d97706;
  }
}

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
