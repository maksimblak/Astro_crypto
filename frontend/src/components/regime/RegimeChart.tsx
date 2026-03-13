import { useMemo, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, LogarithmicScale,
  PointElement, LineElement,
  Tooltip, Legend, Filler,
} from 'chart.js';
import type {
  ChartData,
  ChartOptions,
  Plugin,
  ScriptableLineSegmentContext,
} from 'chart.js';
import type { RegimeHistory } from '../../types/api';
import { fmtDate } from '../../utils/dates';

ChartJS.register(CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement, Tooltip, Legend, Filler);

interface Props {
  history: RegimeHistory[];
}

type Range = '6M' | '1Y' | '2Y' | 'All';

const RANGES: Range[] = ['6M', '1Y', '2Y', 'All'];

function sliceHistory(history: RegimeHistory[], range: Range): RegimeHistory[] {
  if (range === 'All') return history;
  const days = range === '6M' ? 180 : range === '1Y' ? 365 : 730;
  return history.slice(-days);
}

/** Plugin: colored background bands based on direction score zones */
const zonePlugin: Plugin<'line'> = {
  id: 'regimeZones',
  beforeDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea) return;
    const { left, right, top, bottom } = chartArea;
    const yScale = scales['y'];
    if (!yScale) return;

    const zones = [
      { min: 6, max: 18, color: 'rgba(0,255,136,0.04)' },   // bullish
      { min: -18, max: -6, color: 'rgba(255,59,92,0.04)' },  // bearish
    ];

    ctx.save();
    for (const z of zones) {
      const yTop = yScale.getPixelForValue(Math.min(z.max, yScale.max));
      const yBot = yScale.getPixelForValue(Math.max(z.min, yScale.min));
      if (yTop < bottom && yBot > top) {
        ctx.fillStyle = z.color;
        ctx.fillRect(left, Math.max(yTop, top), right - left, Math.min(yBot, bottom) - Math.max(yTop, top));
      }
    }

    // Dashed reference lines at ±6
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    for (const val of [6, -6]) {
      const y = yScale.getPixelForValue(val);
      if (y >= top && y <= bottom) {
        ctx.strokeStyle = val > 0 ? 'rgba(0,255,136,0.15)' : 'rgba(255,59,92,0.15)';
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();
      }
    }
    // Zero line
    const y0 = yScale.getPixelForValue(0);
    if (y0 >= top && y0 <= bottom) {
      ctx.strokeStyle = 'rgba(255,255,255,0.08)';
      ctx.beginPath();
      ctx.moveTo(left, y0);
      ctx.lineTo(right, y0);
      ctx.stroke();
    }
    ctx.restore();
  },
};

const PLUGINS: Plugin<'line'>[] = [zonePlugin];

export default function RegimeChart({ history }: Props) {
  const [range, setRange] = useState<Range>('2Y');
  const filtered = useMemo(() => sliceHistory(history, range), [history, range]);

  const chartData = useMemo<ChartData<'line', number[], string>>(() => ({
    labels: filtered.map(h => h.date),
    datasets: [
      {
        label: 'Direction',
        data: filtered.map(h => h.direction_score ?? h.regime_score ?? 0),
        yAxisID: 'y',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.18,
        fill: 'origin' as const,
        backgroundColor: 'rgba(0,212,255,0.06)',
        segment: {
          borderColor: (ctx: ScriptableLineSegmentContext) =>
            (ctx.p1.parsed.y ?? 0) >= 0
              ? 'rgba(0,255,136,0.85)'
              : 'rgba(255,59,92,0.85)',
        },
        borderColor: 'rgba(0,212,255,0.85)',
      },
      {
        label: 'Stress',
        data: filtered.map(h => h.stress_score),
        yAxisID: 'y',
        borderColor: 'rgba(245,158,11,0.75)',
        backgroundColor: 'rgba(245,158,11,0.06)',
        borderDash: [6, 6],
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
      {
        label: 'Context',
        data: filtered.map(h => h.context_score),
        yAxisID: 'y',
        borderColor: 'rgba(168,85,247,0.75)',
        backgroundColor: 'rgba(168,85,247,0.06)',
        borderDash: [2, 6],
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
      {
        label: 'BTC',
        data: filtered.map(h => h.close),
        yAxisID: 'y1',
        borderColor: 'rgba(59,130,246,0.55)',
        pointRadius: 0,
        tension: 0.15,
        borderWidth: 1.5,
      },
    ],
  }), [filtered]);

  const options = useMemo<ChartOptions<'line'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: {
        labels: { color: '#6b7280', font: { size: 11 }, usePointStyle: true, pointStyle: 'line' as const },
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
          title: (items: { dataIndex: number }[]) => {
            if (!items.length) return '';
            return fmtDate(filtered[items[0].dataIndex]?.date ?? '');
          },
          afterBody: (items: { dataIndex: number }[]) => {
            if (!items.length) return [];
            const h = filtered[items[0].dataIndex];
            if (!h) return [];
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
          maxTicksLimit: 12,
          callback: (v: string | number) => {
            const d = filtered[Number(v)]?.date;
            return d ? d.substring(0, 7) : '';
          },
        },
        grid: { display: false },
      },
      y: {
        position: 'left' as const,
        min: -18,
        max: 18,
        ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 10 } },
        grid: { color: 'rgba(255,255,255,0.03)' },
      },
      y1: {
        position: 'right' as const,
        type: 'logarithmic' as const,
        ticks: {
          color: '#4b5563',
          font: { family: 'JetBrains Mono', size: 10 },
          callback: (v: string | number) => '$' + (Number(v) >= 1000 ? (Number(v) / 1000).toFixed(0) + 'k' : v),
        },
        grid: { drawOnChartArea: false },
      },
    },
  }), [filtered]);

  return (
    <div>
      <div className="rg-chart-header">
        <span className="rg-chart-title">Direction / Stress / Context vs BTC</span>
        <div className="rg-range-btns">
          {RANGES.map(r => (
            <button
              key={r}
              className={`rg-range-btn ${r === range ? 'active' : ''}`}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-box chart-box-lg">
        <Line data={chartData} options={options} plugins={PLUGINS} />
      </div>
    </div>
  );
}
