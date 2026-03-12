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
  perp_premium_daily?: number;
  open_interest_z_30d?: number;
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

export interface UpdateStatus {
  last_run?: string;
  status?: string;
  next_run?: string;
}
