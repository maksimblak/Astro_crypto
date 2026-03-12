export function fmtUsd(v: number | null | undefined): string {
  if (v == null) return '\u2014';
  return '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 });
}

export function regimeTone(code: string): 'bull' | 'bear' | 'neutral' {
  if (code === 'bull' || code === 'recovery') return 'bull';
  if (code === 'bear' || code === 'distribution') return 'bear';
  return 'neutral';
}

export function stressTone(tone: string): 'bull' | 'bear' | 'neutral' {
  if (tone === 'bull' || tone === 'bear' || tone === 'neutral') return tone as 'bull' | 'bear' | 'neutral';
  return 'neutral';
}
