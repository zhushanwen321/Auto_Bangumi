import type { DiagnosisReport, PreviewItem } from '#/diagnosis';

export const apiDiagnosis = {
  async getPreview(rssId: number): Promise<PreviewItem[]> {
    const { data } = await axios.get<{ data: PreviewItem[] }>(
      `/api/v1/rss/${rssId}/diagnosis/preview`
    );
    return data.data;
  },

  async scan(rssId: number, animeTitles?: string[]): Promise<DiagnosisReport> {
    const { data } = await axios.post<{ data: DiagnosisReport }>(
      `/api/v1/rss/${rssId}/diagnosis/scan`,
      {
        anime_titles: animeTitles,
      }
    );
    return data.data;
  },

  async fix(
    action: string,
    torrentName: string,
    params: Record<string, any>
  ): Promise<boolean> {
    const { data } = await axios.post<{ data: { success: boolean } }>(
      '/api/v1/diagnosis/fix',
      {
        action,
        torrent_name: torrentName,
        params,
      }
    );
    return data.data.success;
  },
};
