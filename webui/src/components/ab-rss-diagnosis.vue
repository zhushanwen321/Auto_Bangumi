<script lang="ts" setup>
import { Close, Down, Right } from '@icon-park/vue-next';
import { NSpin } from 'naive-ui';
import type {
  AnimeDiagnosis,
  DiagnosisReport,
  PreviewItem,
  TorrentDiagnosis,
} from '#/diagnosis';
import { apiDiagnosis } from '@/api/diagnosis';

const { t } = useMyI18n();

const props = defineProps<{
  rssId: number;
  rssName: string;
}>();

const show = defineModel<boolean>({ default: false });
const message = useMessage();

type Step = 'preview' | 'scanning' | 'report';
const step = ref<Step>('preview');

// Preview state
const previewLoading = ref(false);
const previewList = ref<PreviewItem[]>([]);
const selectedTitles = ref<string[]>([]);

// Scan state
const scanLoading = ref(false);
const report = ref<DiagnosisReport | null>(null);

// Fix state
const fixingTorrent = ref<string | null>(null);

const allSelected = computed(() => {
  return (
    previewList.value.length > 0 &&
    selectedTitles.value.length === previewList.value.length
  );
});

function toggleSelectAll() {
  if (allSelected.value) {
    selectedTitles.value = [];
  } else {
    selectedTitles.value = previewList.value.map((item) => item.title);
  }
}

function toggleTitle(title: string) {
  const idx = selectedTitles.value.indexOf(title);
  if (idx >= 0) {
    selectedTitles.value.splice(idx, 1);
  } else {
    selectedTitles.value.push(title);
  }
}

watch(show, async (val) => {
  if (val) {
    resetState();
    await loadPreview();
  }
});

function resetState() {
  step.value = 'preview';
  previewList.value = [];
  selectedTitles.value = [];
  report.value = null;
  fixingTorrent.value = null;
}

async function loadPreview() {
  previewLoading.value = true;
  try {
    previewList.value = await apiDiagnosis.getPreview(props.rssId);
  } catch {
    message.error(t('rss.diagnosis.no_data'));
    show.value = false;
  } finally {
    previewLoading.value = false;
  }
}

async function startScan() {
  if (selectedTitles.value.length === 0) {
    message.warning(t('rss.diagnosis.anime_titles_label'));
    return;
  }
  step.value = 'scanning';
  scanLoading.value = true;
  try {
    report.value = await apiDiagnosis.scan(
      props.rssId,
      selectedTitles.value,
    );
    step.value = 'report';
  } catch {
    message.error(t('rss.diagnosis.fix_failed'));
    step.value = 'preview';
  } finally {
    scanLoading.value = false;
  }
}

async function executeFix(action: string, torrentName: string, params: Record<string, any>) {
  fixingTorrent.value = torrentName;
  try {
    const success = await apiDiagnosis.fix(action, torrentName, params);
    if (success) {
      message.success(t('rss.diagnosis.fix_success'));
    } else {
      message.error(t('rss.diagnosis.fix_failed'));
    }
  } catch {
    message.error(t('rss.diagnosis.fix_failed'));
  } finally {
    fixingTorrent.value = null;
  }
}

function statusTagType(status: string): 'active' | 'warn' | 'inactive' | 'primary' {
  switch (status) {
    case 'matched':
    case 'ok':
    case 'active':
      return 'active';
    case 'unmatched':
    case 'warning':
      return 'primary';
    case 'error':
    case 'unparsed':
      return 'warn';
    default:
      return 'inactive';
  }
}

function animeStatusText(status: string): string {
  switch (status) {
    case 'ok': return t('rss.diagnosis.no_issues');
    case 'warning': return 'Warning';
    case 'error': return 'Error';
    default: return status;
  }
}

function booleanTag(val: boolean | null): 'active' | 'warn' | 'inactive' {
  if (val === true) return 'active';
  if (val === false) return 'warn';
  return 'inactive';
}

function booleanText(val: boolean | null): string {
  if (val === true) return 'Yes';
  if (val === false) return 'No';
  return 'N/A';
}

function close() {
  show.value = false;
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="show" class="diag-backdrop" @click.self="close">
        <div class="diag-modal" role="dialog" aria-modal="true">
          <!-- Header -->
          <header class="diag-header">
            <h2 class="diag-title">
              {{ t('rss.diagnosis.title') }} - {{ rssName }}
            </h2>
            <button class="close-btn" :aria-label="t('rss.diagnosis.close')" @click="close">
              <Close theme="outline" size="18" />
            </button>
          </header>

          <!-- Step: Preview -->
          <template v-if="step === 'preview'">
            <div class="diag-content">
              <NSpin :show="previewLoading">
                <!-- Empty state -->
                <div v-if="!previewLoading && previewList.length === 0" class="diag-empty">
                  {{ t('rss.diagnosis.rss_not_found') }}
                </div>

                <!-- Select all -->
                <div v-else class="diag-select-all">
                  <label class="diag-checkbox-row">
                    <input
                      type="checkbox"
                      :checked="allSelected"
                      @change="toggleSelectAll"
                    />
                    <span class="diag-select-all-text">
                      {{ allSelected ? t('rss.diagnosis.deselect_all') : t('rss.diagnosis.select_all') }} ({{ selectedTitles.length }}/{{ previewList.length }})
                    </span>
                  </label>
                </div>

                <!-- Anime list -->
                <div v-if="previewList.length > 0" class="diag-list">
                  <label
                    v-for="item in previewList"
                    :key="item.title"
                    class="diag-checkbox-row diag-anime-item"
                  >
                    <input
                      type="checkbox"
                      :checked="selectedTitles.includes(item.title)"
                      @change="toggleTitle(item.title)"
                    />
                    <span class="diag-anime-title">{{ item.title }}</span>
                    <span class="diag-anime-meta">
                      <ab-tag :type="statusTagType(item.status)" :title="item.status" />
                      <span class="diag-torrent-count">{{ t('rss.diagnosis.torrent_count', { count: item.torrent_count }) }}</span>
                    </span>
                  </label>
                </div>
              </NSpin>
            </div>

            <footer class="diag-footer">
              <ab-button
                size="small"
                :disabled="selectedTitles.length === 0"
                @click="startScan"
              >
                {{ t('rss.diagnosis.start_scan') }}
              </ab-button>
            </footer>
          </template>

          <!-- Step: Scanning -->
          <template v-else-if="step === 'scanning'">
            <div class="diag-content diag-content--center">
              <NSpin :show="scanLoading" />
              <p class="diag-scanning-text">{{ t('rss.diagnosis.scanning') }}</p>
            </div>
          </template>

          <!-- Step: Report -->
          <template v-else-if="step === 'report' && report">
            <div class="diag-content">
              <!-- Global errors -->
              <div v-if="report.errors.length > 0" class="diag-errors">
                <div v-for="(err, i) in report.errors" :key="i" class="diag-error-item">
                  {{ err }}
                </div>
              </div>

              <!-- Anime groups -->
              <div class="diag-report-list">
                <div
                  v-for="anime in report.anime_list"
                  :key="anime.anime_title"
                  class="diag-anime-group"
                >
                  <div class="diag-anime-group-header">
                    <span class="diag-anime-group-title">{{ anime.anime_title }}</span>
                    <ab-tag :type="statusTagType(anime.status)" :title="animeStatusText(anime.status)" />
                  </div>

                  <!-- Torrents -->
                  <div class="diag-torrent-list">
                    <div
                      v-for="torrent in anime.torrents"
                      :key="torrent.torrent_name"
                      class="diag-torrent-item"
                      :class="{ 'diag-torrent-item--error': torrent.issues.length > 0 }"
                    >
                      <div class="diag-torrent-name" :title="torrent.torrent_name">
                        {{ torrent.torrent_name }}
                      </div>
                      <div class="diag-torrent-tags">
                        <ab-tag
                          :type="torrent.parse_result ? 'active' : 'warn'"
                          :title="torrent.parse_result ? t('rss.diagnosis.parse_ok') : t('rss.diagnosis.parse_fail')"
                        />
                        <ab-tag
                          :type="torrent.match_result ? 'active' : 'inactive'"
                          :title="torrent.match_result ? t('rss.diagnosis.match_ok') : t('rss.diagnosis.match_fail')"
                        />
                        <ab-tag
                          :type="booleanTag(torrent.filter_passed)"
                          :title="torrent.filter_passed ? t('rss.diagnosis.filter_pass') : t('rss.diagnosis.filter_block')"
                        />
                        <ab-tag
                          :type="torrent.downloaded ? 'active' : 'inactive'"
                          :title="torrent.downloaded ? t('rss.diagnosis.download_ok') : t('rss.diagnosis.download_fail')"
                        />
                      </div>

                      <!-- Issues -->
                      <div v-if="torrent.issues.length > 0" class="diag-issues">
                        <div
                          v-for="(issue, idx) in torrent.issues"
                          :key="idx"
                          class="diag-issue"
                        >
                          <span class="diag-issue-step">[{{ issue.step }}]</span>
                          <span class="diag-issue-msg">{{ issue.message }}</span>
                        </div>
                      </div>

                      <!-- Filter reason -->
                      <div v-if="torrent.filter_reason" class="diag-filter-reason">
                        {{ t('rss.diagnosis.filter_block') }}: {{ torrent.filter_reason }}
                      </div>

                      <!-- Fix actions -->
                      <div v-if="anime.fix_actions.length > 0" class="diag-fix-actions">
                        <ab-button
                          v-for="(fix, fixIdx) in anime.fix_actions.filter(f => f.torrent_name === torrent.torrent_name)"
                          :key="fixIdx"
                          size="small"
                          type="secondary"
                          :loading="fixingTorrent === torrent.torrent_name"
                          @click="executeFix(fix.action, fix.torrent_name, fix.params)"
                        >
                          {{ t('rss.diagnosis.fix_button') }}: {{ fix.action }}
                        </ab-button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <footer class="diag-footer diag-footer--report">
              <ab-button size="small" type="secondary" @click="step = 'preview'">
                {{ t('rss.diagnosis.back') }}
              </ab-button>
            </footer>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.diag-backdrop {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-overlay);
  z-index: var(--z-modal);
  padding: 16px;
}

.diag-modal {
  width: 100%;
  max-width: 680px;
  max-height: 85dvh;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  overflow: hidden;

  @supports not (max-height: 1dvh) {
    max-height: 85vh;
  }
}

.diag-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
}

.diag-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  flex-shrink: 0;

  &:hover {
    background: var(--color-surface-hover);
    color: var(--color-text);
  }
}

.diag-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;

  &--center {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    min-height: 200px;
  }
}

.diag-empty {
  text-align: center;
  color: var(--color-text-muted);
  padding: 40px 0;
}

// Preview list
.diag-select-all {
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 8px;
}

.diag-checkbox-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;

  input[type="checkbox"] {
    accent-color: var(--color-primary);
    width: 16px;
    height: 16px;
    flex-shrink: 0;
  }
}

.diag-select-all-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.diag-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diag-anime-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-md);
  transition: background-color var(--transition-fast);

  &:hover {
    background: var(--color-surface-hover);
  }
}

.diag-anime-title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diag-anime-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.diag-torrent-count {
  font-size: 12px;
  color: var(--color-text-muted);
  white-space: nowrap;
}

// Scanning
.diag-scanning-text {
  font-size: 14px;
  color: var(--color-text-secondary);
}

// Report
.diag-errors {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.diag-error-item {
  padding: 8px 12px;
  background: color-mix(in srgb, var(--color-danger) 10%, transparent);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--color-danger);
}

.diag-report-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.diag-anime-group {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.diag-anime-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  background: var(--color-surface-hover);
  border-bottom: 1px solid var(--color-border);
}

.diag-anime-group-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.diag-torrent-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.diag-torrent-item {
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-border);

  &:last-child {
    border-bottom: none;
  }

  &--error {
    background: color-mix(in srgb, var(--color-danger) 4%, transparent);
  }
}

.diag-torrent-name {
  font-size: 13px;
  color: var(--color-text);
  word-break: break-all;
  margin-bottom: 6px;
}

.diag-torrent-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.diag-issues {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diag-issue {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: flex;
  gap: 6px;
}

.diag-issue-step {
  font-weight: 500;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.diag-filter-reason {
  margin-top: 6px;
  font-size: 12px;
  color: var(--color-warning);
}

.diag-fix-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

// Footer
.diag-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--color-border);

  &--report {
    justify-content: flex-start;
  }
}

// Modal transition
.modal-enter-active,
.modal-leave-active {
  transition: opacity 200ms ease;

  .diag-modal {
    transition: transform 200ms ease, opacity 200ms ease;
  }
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;

  .diag-modal {
    transform: scale(0.95) translateY(10px);
    opacity: 0;
  }
}
</style>
