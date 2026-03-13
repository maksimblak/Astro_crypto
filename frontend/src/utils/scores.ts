import type { ScoreScale } from '../types/api';

export const DEFAULT_SCORE_SCALE: ScoreScale = {
  cool: 0.5,
  warm: 1.0,
  hot: 1.5,
  extreme: 2.0,
};

export function normalizeScoreScale(scale?: Partial<ScoreScale> | null): ScoreScale {
  return {
    cool: scale?.cool != null ? Number(scale.cool) : DEFAULT_SCORE_SCALE.cool,
    warm: scale?.warm != null ? Number(scale.warm) : DEFAULT_SCORE_SCALE.warm,
    hot: scale?.hot != null ? Number(scale.hot) : DEFAULT_SCORE_SCALE.hot,
    extreme: scale?.extreme != null ? Number(scale.extreme) : DEFAULT_SCORE_SCALE.extreme,
  };
}

export function scoreClass(s: number, scale: ScoreScale = DEFAULT_SCORE_SCALE): string {
  if (s >= scale.hot) return 'hot';
  if (s >= scale.warm) return 'warm';
  if (s >= scale.cool) return 'cool';
  return 'cold';
}

export function scoreBarColor(s: number, scale: ScoreScale = DEFAULT_SCORE_SCALE): string {
  if (s >= scale.extreme) return 'rgba(255,59,92,0.92)';
  if (s >= scale.hot) return 'rgba(255,107,53,0.88)';
  if (s >= scale.warm) return 'rgba(245,158,11,0.82)';
  if (s >= scale.cool) return 'rgba(0,212,255,0.62)';
  return 'rgba(75,85,99,0.4)';
}

export function scoreBarBorder(s: number, scale: ScoreScale = DEFAULT_SCORE_SCALE): string {
  if (s >= scale.extreme) return '#ff3b5c';
  if (s >= scale.hot) return '#ff6b35';
  if (s >= scale.warm) return '#f59e0b';
  if (s >= scale.cool) return '#00d4ff';
  return '#4b5563';
}

export function riskClass(s: number, scale: ScoreScale = DEFAULT_SCORE_SCALE): string {
  if (s >= scale.hot) return 'hot';
  if (s >= scale.warm) return 'warm';
  return 'mild';
}
