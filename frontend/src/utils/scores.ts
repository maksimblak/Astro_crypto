import type { ScoreScale } from '../types/api';

let thresholds: ScoreScale = { cool: 0.5, warm: 1.0, hot: 1.5, extreme: 2.0 };

export function setScoreThresholds(scale: ScoreScale) {
  thresholds = {
    cool: scale.cool != null ? Number(scale.cool) : thresholds.cool,
    warm: scale.warm != null ? Number(scale.warm) : thresholds.warm,
    hot: scale.hot != null ? Number(scale.hot) : thresholds.hot,
    extreme: scale.extreme != null ? Number(scale.extreme) : thresholds.extreme,
  };
}

export function getThresholds(): ScoreScale {
  return thresholds;
}

export function scoreClass(s: number): string {
  if (s >= thresholds.hot) return 'hot';
  if (s >= thresholds.warm) return 'warm';
  if (s >= thresholds.cool) return 'cool';
  return 'cold';
}

export function scoreBarColor(s: number): string {
  if (s >= thresholds.extreme) return 'rgba(255,59,92,0.92)';
  if (s >= thresholds.hot) return 'rgba(255,107,53,0.88)';
  if (s >= thresholds.warm) return 'rgba(245,158,11,0.82)';
  if (s >= thresholds.cool) return 'rgba(0,212,255,0.62)';
  return 'rgba(75,85,99,0.4)';
}

export function scoreBarBorder(s: number): string {
  if (s >= thresholds.extreme) return '#ff3b5c';
  if (s >= thresholds.hot) return '#ff6b35';
  if (s >= thresholds.warm) return '#f59e0b';
  if (s >= thresholds.cool) return '#00d4ff';
  return '#4b5563';
}

export function riskClass(s: number): string {
  if (s >= thresholds.hot) return 'hot';
  if (s >= thresholds.warm) return 'warm';
  return 'mild';
}
