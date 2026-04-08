<script lang="ts" setup>
import { Caution } from '@icon-park/vue-next';
import type { SettingItem } from '#/components';
import type { ExperimentalOpenAI, OpenAIType } from '#/config';

const { t } = useMyI18n();
const { getSettingGroup } = useConfigStore();

const openAI = getSettingGroup('experimental_openai');
const dandanplay = getSettingGroup('dandanplay');
const openAITypes: OpenAIType = ['openai', 'azure'];

const providerItems: SettingItem<ExperimentalOpenAI>[] = [
  {
    configKey: 'api_type',
    label: () => t('config.experimental_openai_set.api_type'),
    type: 'select',
    prop: {
      items: openAITypes,
    },
  },
  {
    configKey: 'api_key',
    label: () => t('config.experimental_openai_set.api_key'),
    type: 'input',
    prop: {
      type: 'password',
      placeholder: 'sk-...',
    },
  },
  {
    configKey: 'api_base',
    label: () => t('config.experimental_openai_set.api_base'),
    type: 'input',
    prop: {
      type: 'url',
      placeholder: 'https://api.openai.com/v1',
    },
  },
  {
    configKey: 'model',
    label: () => t('config.experimental_openai_set.model'),
    type: 'input',
    prop: {
      type: 'text',
      placeholder: 'gpt-4o-mini',
    },
  },
];

const azureItems: SettingItem<ExperimentalOpenAI>[] = [
  {
    configKey: 'api_version',
    label: () => t('config.experimental_openai_set.api_version'),
    type: 'input',
    prop: {
      type: 'text',
      placeholder: '2024-02-01',
    },
  },
  {
    configKey: 'deployment_id',
    label: () => t('config.experimental_openai_set.deployment_id'),
    type: 'input',
    prop: {
      type: 'text',
      placeholder: 'gpt-4o',
    },
  },
];

const featureItems = [
  {
    key: 'enable_title_enhancement' as const,
    label: () => t('config.experimental_openai_set.enable_title_enhancement'),
  },
  {
    key: 'enable_rss_match' as const,
    label: () => t('config.experimental_openai_set.enable_rss_match'),
  },
  {
    key: 'enable_dandanplay_match' as const,
    label: () => t('config.experimental_openai_set.enable_dandanplay_match'),
  },
];
</script>

<template>
  <ab-fold-panel :title="$t('config.experimental_openai_set.title')">
    <div class="openai-section">
      <div class="openai-notice">
        <Caution size="16" />
        <span>{{ $t('config.experimental_openai_set.warning') }}</span>
      </div>

      <ab-setting
        v-model:data="openAI.enable"
        config-key="enable"
        :label="() => t('config.experimental_openai_set.enable')"
        type="switch"
      />

      <transition name="slide-fade">
        <div v-if="openAI.enable" class="openai-config">
          <ab-setting
            v-for="i in providerItems"
            :key="i.configKey"
            v-bind="i"
            v-model:data="openAI[i.configKey]"
          />

          <template v-if="openAI.api_type === 'azure'">
            <ab-setting
              v-for="i in azureItems"
              :key="i.configKey"
              v-bind="i"
              v-model:data="openAI[i.configKey]"
            />
          </template>

          <div class="section-divider"></div>
          <div class="section-label">
            {{ $t('config.experimental_openai_set.features_title') }}
          </div>

          <ab-setting
            v-for="f in featureItems"
            :key="f.key"
            v-model:data="openAI.features[f.key]"
            :config-key="f.key"
            :label="f.label"
            type="switch"
          />

          <div class="section-divider"></div>
          <div class="section-label">
            {{ $t('config.experimental_openai_set.dandanplay_title') }}
          </div>

          <ab-setting
            v-model:data="dandanplay.app_id"
            config-key="app_id"
            :label="() => t('config.experimental_openai_set.app_id')"
            type="input"
            :prop="{ type: 'text', placeholder: 'App ID' }"
          />
          <ab-setting
            v-model:data="dandanplay.app_secret"
            config-key="app_secret"
            :label="() => t('config.experimental_openai_set.app_secret')"
            type="input"
            :prop="{ type: 'password', placeholder: 'App Secret' }"
          />
        </div>
      </transition>
    </div>
  </ab-fold-panel>
</template>

<style lang="scss" scoped>
.openai-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.openai-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
  color: var(--color-warning);
  font-size: 12px;
  transition: background-color var(--transition-normal),
    border-color var(--transition-normal);
}

.openai-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
}

.section-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 0;
}

.section-label {
  font-size: 11px;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.slide-fade-enter-active {
  transition: all 0.2s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.15s ease-in;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
