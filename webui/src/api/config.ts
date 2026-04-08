import type { Config, ExperimentalOpenAI } from '#/config';
import type { ApiSuccess } from '#/api';

export interface TestOpenAIResponse {
  success: boolean;
  message_en: string;
  message_zh: string;
}

export const apiConfig = {
  /**
   * 获取 config 数据
   */
  async getConfig() {
    const { data } = await axios.get<Config>('api/v1/config/get');
    return data;
  },

  /**
   * 更新 config 数据
   * @param newConfig - 需要更新的 config
   */
  async updateConfig(newConfig: Config) {
    const { data } = await axios.patch<ApiSuccess>(
      'api/v1/config/update',
      newConfig
    );
    return data;
  },

  /**
   * 测试 OpenAI 连接（使用当前表单中的配置，不会保存）
   */
  async testOpenAI(config: ExperimentalOpenAI) {
    const { data } = await axios.post<TestOpenAIResponse>(
      'api/v1/config/test-openai',
      {
        api_key: config.api_key,
        api_base: config.api_base,
        api_type: config.api_type,
        api_version: config.api_version,
        model: config.model,
        deployment_id: config.deployment_id,
      }
    );
    return data;
  },
};
