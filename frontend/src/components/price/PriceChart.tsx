import { useMemo } from 'react';
import { Chart } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement,
  BubbleController,
  Tooltip, Legend, Filler,
} from 'chart.js';
import type { ScriptableContext } from 'chart.js';
import type { DailyPrice, PivotPoint } from '../../types/api';

ChartJS.register(
  CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement,
  BubbleController,
  Tooltip, Legend, Filler,
);

interface Props {
  daily: DailyPrice[];
  pivots: PivotPoint[];
}

function pts(arr: PivotPoint[]) {
  return arr.map(p => ({
    x: p.date,
    y: p.price,
    r: Math.max(4, Math.min(12, (p.tension_count || 0) * 1.5 + (p.near_eclipse || 0) * 3)),
  }));
}

export default function PriceChart({ daily, pivots }: Props) {
  const highs = useMemo(() => pivots.filter(p => p.is_high === 1), [pivots]);
  const lows = useMemo(() => pivots.filter(p => p.is_high === 0), [pivots]);

  const chartData = useMemo(() => ({
    labels: daily.map(d => d.date),
    datasets: [
      {
        label: 'BTC',
        type: 'line' as const,
        data: daily.map(d => d.close),
        borderColor: 'rgba(59,130,246,0.8)',
        backgroundColor: (ctx: ScriptableContext<'line'>) => {
          const chart = ctx.chart;
          const { ctx: canvasCtx, chartArea } = chart;
          if (!chartArea) return 'rgba(59,130,246,0.15)';
          const g = canvasCtx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          g.addColorStop(0, 'rgba(59,130,246,0.15)');
          g.addColorStop(1, 'rgba(59,130,246,0)');
          return g;
        },
        borderWidth: 1.5,
        pointRadius: 0,
        fill: true,
        tension: 0.1,
        order: 2,
      },
      {
        label: 'Пики',
        type: 'bubble' as const,
        data: pts(highs),
        backgroundColor: 'rgba(255,59,92,0.6)',
        borderColor: '#ff3b5c',
        borderWidth: 1.5,
        order: 1,
      },
      {
        label: 'Дно',
        type: 'bubble' as const,
        data: pts(lows),
        backgroundColor: 'rgba(0,255,136,0.5)',
        borderColor: '#00ff88',
        borderWidth: 1.5,
        order: 1,
      },
    ],
  }), [daily, highs, lows]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'nearest' as const, intersect: false },
    plugins: {
      legend: {
        labels: { color: '#9ca3af', font: { size: 12 }, usePointStyle: true, pointStyle: 'circle' as const },
      },
      tooltip: {
        backgroundColor: 'rgba(17,24,39,0.95)',
        borderColor: 'rgba(59,130,246,0.2)',
        borderWidth: 1,
        titleColor: '#e8eaed',
        bodyColor: '#9ca3af',
        padding: 12,
        cornerRadius: 10,
        callbacks: {
          label: (ctx: { dataset: { type?: string; label?: string }; raw: unknown; parsed: { y: number } }) => {
            if (ctx.dataset.type === 'bubble') {
              const raw = ctx.raw as { x: string; y: number };
              return `${ctx.dataset.label}: $${raw.y.toLocaleString()} (${raw.x})`;
            }
            return `BTC: $${ctx.parsed.y.toLocaleString()}`;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: '#4b5563',
          maxTicksLimit: 20,
          callback: (v: string | number) => {
            const d = daily[Number(v)]?.date;
            return d ? d.substring(0, 7) : '';
          },
        },
        grid: { display: false },
      },
      y: {
        type: 'logarithmic' as const,
        ticks: {
          color: '#4b5563',
          font: { family: 'JetBrains Mono', size: 11 },
          callback: (v: string | number) => '$' + (Number(v) >= 1000 ? (Number(v) / 1000).toFixed(0) + 'k' : v),
        },
        grid: { color: 'rgba(255,255,255,0.04)' },
      },
    },
  }), [daily]);

  return (
    <div className="section" id="sectionChart">
      <div className="section-head">
        <div className="section-title">
          <span className="dot" style={{ background: 'var(--neon-blue)', boxShadow: '0 0 20px rgba(59,130,246,0.3)' }} />
          Цена BTC и развороты
        </div>
      </div>
      <div className="card">
        <div className="chart-box chart-box-lg">
          <Chart type="line" data={chartData as never} options={options as never} />
        </div>
      </div>
    </div>
  );
}
