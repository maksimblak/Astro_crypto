import type { Signal } from '../../types/api';

interface Props {
  signal: Signal;
}

export default function SignalCard({ signal }: Props) {
  return (
    <div className={`signal-card ${signal.tone}`}>
      <div className="signal-label">{signal.label}</div>
      <div className={`signal-value ${signal.tone}`}>{signal.value}</div>
      <div className="signal-note">{signal.note}</div>
    </div>
  );
}
