<script lang="ts" setup>
import type { SettingItem } from '#/components';
import type { DandanplayConfig } from '#/config';

const { t } = useMyI18n();
const { getSettingGroup } = useConfigStore();

const dandanplay = getSettingGroup('dandanplay');

const items: SettingItem<DandanplayConfig>[] = [
  {
    configKey: 'app_id',
    label: () => t('config.dandanplay_set.app_id'),
    type: 'input',
    prop: {
      type: 'text',
      placeholder: 'AppId',
    },
  },
  {
    configKey: 'app_secret',
    label: () => t('config.dandanplay_set.app_secret'),
    type: 'input',
    prop: {
      type: 'password',
      placeholder: 'AppSecret',
    },
  },
];
</script>

<template>
  <ab-fold-panel :title="$t('config.dandanplay_set.title')">
    <div class="dandanplay-section">
      <ab-setting
        v-model:data="dandanplay.enable"
        config-key="enable"
        :label="() => t('config.dandanplay_set.enable')"
        type="switch"
      />

      <transition name="slide-fade">
        <div v-if="dandanplay.enable" class="dandanplay-config">
          <ab-setting
            v-for="i in items"
            :key="i.configKey"
            v-bind="i"
            v-model:data="dandanplay[i.configKey]"
          />
        </div>
      </transition>
    </div>
  </ab-fold-panel>
</template>

<style lang="scss" scoped>
.dandanplay-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dandanplay-config {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 4px;
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
