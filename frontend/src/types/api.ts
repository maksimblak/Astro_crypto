export interface TodayData {
  date: string;
  score: number;
  direction: number;
  moon_sign: string;
  moon_element: string;
  quarter: string;
  eclipse_days: number;
  moon_ingress: number;
  tension: number;
  harmony: number;
  retro_planets: string;
  station_planets: string;
  sun_sign: string;
  sun_element: string;
  details: string;
}

export interface CalendarDay {
  date: string;
  score: number;
  direction: number;
  moon_sign: string;
  moon_element: string;
  quarter: string;
  eclipse_days: number;
  moon_ingress: number;
  tension: number;
  harmony: number;
  retro_planets: string;
  station_planets: string;
  sun_sign: string;
  sun_element: string;
  details: string;
}

export interface DailyPrice {
  date: string;
  close: number;
}

export interface PivotPoint {
  date: string;
  price: number;
  is_high: number;
  tension_count?: number;
  near_eclipse?: number;
}

export interface ThresholdRow {
  threshold: number;
  days_count: number;
  days_pct: number;
  pivots_in_zone: number;
  lift: number;
}

export interface ScoreScale {
  cool: number;
  warm: number;
  hot: number;
  extreme: number;
}

export interface StatsData {
  baseline_avg_score: number;
  pivot_avg_score: number;
  pivot_matched: number;
  total_calendar_days: number;
  total_pivots: number;
  thresholds: ThresholdRow[];
  score_scale: ScoreScale;
  direction_accuracy: number;
  direction_total: number;
  direction_correct: number;
  period_start: string;
  period_end: string;
  period_label: string;
}

export interface Signal {
  label: string;
  value: string;
  tone: 'bull' | 'bear' | 'neutral';
  note: string;
}

export interface RegimeMetrics {
  momentum_90?: number;
  close_vs_200?: number;
  amihud_z_90d?: number;
  range_compression_20d?: number;
  drawdown_ath?: number;
  wiki_views_z_30d?: number;
  fear_greed_value?: number;
  funding_rate_z_30d?: number;
  funding_price_divergence_3d?: number;
  funding_contrarian_bias_3d?: number;
  perp_premium_daily?: number;
  open_interest_delta_1d?: number;
  open_interest_delta_z_30d?: number;
  oi_price_state_1d?: string;
  open_interest_z_30d?: number;
  dxy_close?: number;
  dxy_return_20d?: number;
  dxy_return_z_90d?: number;
  us10y_yield?: number;
  us10y_change_20d_bps?: number;
  us10y_change_z_90d?: number;
  spx_close?: number;
  btc_spx_corr_30d?: number;
  unique_addresses_z_30d?: number;
}

export interface RegimeHistory {
  date: string;
  close: number;
  direction_score: number;
  regime_score?: number;
  stress_score: number;
  context_score: number;
  regime_label: string;
  confidence: number;
  stress_label: string;
  context_label: string;
  funding_price_divergence_3d?: number;
  open_interest_delta_1d?: number;
  btc_spx_corr_30d?: number;
}

export interface RegimeData {
  regime_code: string;
  regime_label: string;
  summary: string;
  bias: string;
  confidence: number;
  direction_score: number;
  stress_score: number;
  stress_label: string;
  stress_tone: string;
  context_score: number;
  context_label: string;
  context_tone: string;
  setup_score: number;
  setup_label: string;
  setup_summary: string;
  setup_tone: string;
  price: number;
  as_of: string;
  metrics: RegimeMetrics;
  direction_signals: Signal[];
  stress_signals: Signal[];
  context_signals: Signal[];
  history: RegimeHistory[];
  error?: string;
}

export interface CycleMetrics {
  mvrv_zscore?: number | null;
  mvrv_top_threshold?: number | null;
  mvrv_bottom_extreme?: number | null;
  nupl?: number | null;
  nupl_top_threshold?: number | null;
  nupl_bottom_extreme?: number | null;
  puell_multiple?: number | null;
  puell_top_threshold?: number | null;
  puell_bottom_extreme?: number | null;
  pi_sma111?: number | null;
  pi_sma350x2?: number | null;
  pi_cycle_signal?: number | null;
  hashrate_sma_30?: number | null;
  hashrate_sma_60?: number | null;
  hashribbon_trend?: string | null;
  hashribbon_buy_signal?: number | null;
}

export interface CycleHistory {
  date: string;
  price?: number | null;
  top_score: number;
  bottom_score: number;
  cycle_bias: number;
  cycle_zone: string;
  mvrv_zscore?: number | null;
  nupl?: number | null;
  puell_multiple?: number | null;
  pi_cycle_signal?: number | null;
  hashribbon_buy_signal?: number | null;
}

export interface CycleData {
  as_of: string;
  price?: number | null;
  cycle_zone: string;
  cycle_label: string;
  cycle_tone: 'bull' | 'bear' | 'neutral';
  summary: string;
  top_score: number;
  bottom_score: number;
  cycle_bias: number;
  metrics: CycleMetrics;
  signals: Signal[];
  history: CycleHistory[];
}

export interface UpdateStatus {
  enabled: boolean;
  running: boolean;
  interval_seconds: number;
  startup_delay_seconds: number;
  last_started_at?: string | null;
  last_finished_at?: string | null;
  last_success_at?: string | null;
  last_error?: string | null;
  last_stage?: string | null;
  log_path: string;
  status_path: string;
}
