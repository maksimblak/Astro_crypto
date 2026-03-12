import { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, LogarithmicScale,
  PointElement, LineElement,
  Tooltip, Legend, Filler,
} from 'chart.js';
import type { RegimeHistory } from '../../types/api';
import { fmtDate } from '../../utils/dates';

ChartJS.register(CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement, Tooltip, Legend, Filler);

interface Props {
  history: RegimeHistory[];
}

export default function RegimeChart({ history }: Props) {
  const chartData = useMemo(() => ({
    labels: history.map(h => h.date),
    datasets: [
      {
        label: 'Direction score',
        data: history.map(h => h.direction_score ?? h.regime_score),
        yAxisID: 'y',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.18,
        fill: 'origin' as const,
        backgroundColor: 'rgba(0,212,255,0.08)',
        segment: {
          borderColor: (ctx: { p1: { parsed: { y: number } } }) =>
            ctx.p1.parsed.y >= 0 ? 'rgba(0,255,136,0.85)' : 'rgba(255,59,92,0.85)',
        },
        borderColor: 'rgba(0,212,255,0.85)',
      },
      {
        label: 'Stress score',
        data: history.map(h => h.stress_score),
        yAxisID: 'y',
        borderColor: 'rgba(245,158,11,0.9)',
        backgroundColor: 'rgba(245,158,11,0.10)',
        borderDash: [6, 6],
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
      {
        label: 'Context score',
        data: history.map(h => h.context_score),
        yAxisID: 'y',
        borderColor: 'rgba(168,85,247,0.9)',
        backgroundColor: 'rgba(168,85,247,0.08)',
        borderDash: [2, 6],
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
      {
        label: 'BTC',
        data: history.map(h => h.close),
        yAxisID: 'y1',
        borderColor: 'rgba(59,130,246,0.65)',
        pointRadius: 0,
        tension: 0.15,
        borderWidth: 1.5,
      },
    ],
  }), [history]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: {
        labels: { color: '#9ca3af', font: { size: 12 }, usePointStyle: true, pointStyle: 'line' as const },
      },
      tooltip: {
        backgroundColor: 'rgba(17,24,39,0.95)',
        borderColor: 'rgba(0,212,255,0.2)',
        borderWidth: 1,
        titleColor: '#e8eaed',
        bodyColor: '#9ca3af',
        padding: 12,
        cornerRadius: 10,
        callbacks: {
          title: (items: { dataIndex: number }[]) => fmtDate(history[items[0].dataIndex].date),
          afterBody: (items: { dataIndex: number }[]) => {
            const h = history[items[0].dataIndex];
            return [
              `Режим: ${h.regime_label}`,
              `Direction: ${h.direction_score ?? h.regime_score}`,
              `Confidence: ${h.confidence}%`,
              `Stress: ${h.stress_score} (${h.stress_label})`,
              `Context: ${h.context_score} (${h.context_label})`,
            ];
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#4b5563',
          maxTicksLimit: 14,
          callback: function (this: { getLabelForValue(v: number): string }, v: string | number) {
            const d = this.getLabelForValue(v as number);
            return d ? d.substring(0, 7) : '';
          },
        },
        grid: { display: false },
      },
      y: {
        position: 'left' as const,
        min: -18,
        max: 18,
        ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 11 } },
        grid: { color: 'rgba(255,255,255,0.04)' },
      },
      y1: {
        position: 'right' as const,
        type: 'logarithmic' as const,
        ticks: {
          color: '#4b5563',
          font: { family: 'JetBrains Mono', size: 11 },
          callback: (v: string | number) => '$' + (Number(v) >= 1000 ? (Number(v) / 1000).toFixed(0) + 'k' : v),
        },
        grid: { drawOnChartArea: false },
      },
    },
  }), [history]);

  return (
    <div className="chart-box chart-box-lg">
      <Line data={chartData} options={options as never} />
    </div>
  );
}
