export interface PreviewItem {
  title: string;
  bangumi_id: number | null;
  torrent_count: number;
  status: 'matched' | 'unmatched' | 'unparsed';
}

export interface DiagnosisIssue {
  step: string;
  severity: string;
  message: string;
}

export interface TorrentDiagnosis {
  torrent_name: string;
  parse_result: any | null;
  match_result: any | null;
  filter_passed: boolean | null;
  filter_reason: string | null;
  downloaded: boolean;
  issues: DiagnosisIssue[];
}

export interface FixAction {
  action: string;
  torrent_name: string;
  params: Record<string, any>;
}

export interface AnimeDiagnosis {
  anime_title: string;
  bangumi_id: number | null;
  status: 'ok' | 'warning' | 'error';
  torrents: TorrentDiagnosis[];
  fix_actions: FixAction[];
}

export interface DiagnosisReport {
  rss_id: number;
  rss_url: string;
  scanned_at: string;
  anime_list: AnimeDiagnosis[];
  errors: string[];
}
