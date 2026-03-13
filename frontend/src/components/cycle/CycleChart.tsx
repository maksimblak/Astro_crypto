import { useMemo, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import type { ChartData, ChartOptions, Plugin } from 'chart.js';
import type { CycleHistory } from '../../types/api';
import { fmtDate } from '../../utils/dates';
import { zoneLabel } from './cycleUtils';

ChartJS.register(CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement, Tooltip, Legend, Filler);

interface Props {
  history: CycleHistory[];
}

type Range = '1Y' | '2Y' | 'ALL';

/** Chart.js plugin: paint score-zone background bands */
const zonePlugin: Plugin<'line'> = {
  id: 'zoneBackground',
  beforeDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    if (!chartArea || !scales['y']) return;
    const { top, bottom, left, right } = chartArea;
    const yScale = scales['y'];

    const bands: { lo: number; hi: number; color: string }[] = [
      { lo: 0.70, hi: 1.05, color: 'rgba(255,59,92,0.06)' },   // top zone
      { lo: 0.45, hi: 0.70, color: 'rgba(255,170,60,0.04)' },   // watch
    ];

    ctx.save();
    for (const b of bands) {
      const y1 = yScale.getPixelForValue(b.hi);
      const y2 = yScale.getPixelForValue(b.lo);
      ctx.fillStyle = b.color;
      ctx.fillRect(left, Math.max(y1, top), right - left, Math.min(y2, bottom) - Math.max(y1, top));
    }

    // dashed threshold lines
    const thresholds = [
      { val: 0.70, color: 'rgba(255,59,92,0.25)' },
      { val: 0.45, color: 'rgba(255,170,60,0.20)' },
    ];
    ctx.setLineDash([6, 4]);
    ctx.lineWidth = 1;
    for (const t of thresholds) {
      const py = yScale.getPixelForValue(t.val);
      if (py >= top && py <= bottom) {
        ctx.strokeStyle = t.color;
        ctx.beginPath();
        ctx.moveTo(left, py);
        ctx.lineTo(right, py);
        ctx.stroke();
      }
    }
    ctx.restore();
  },
};

function filterByRange(history: CycleHistory[], range: Range): CycleHistory[] {
  if (range === 'ALL') return history;
  const now = new Date();
  const cutoff = new Date(now);
  cutoff.setFullYear(cutoff.getFullYear() - (range === '1Y' ? 1 : 2));
  const cutStr = cutoff.toISOString().slice(0, 10);
  return history.filter(h => h.date >= cutStr);
}

export default function CycleChart({ history }: Props) {
  const [range, setRange] = useState<Range>('2Y');

  const filtered = useMemo(() => filterByRange(history, range), [history, range]);

  const chartData = useMemo<ChartData<'line', number[], string>>(() => ({
    labels: filtered.map(point => point.date),
    datasets: [
      {
        label: 'Top score',
        data: filtered.map(point => point.top_score),
        yAxisID: 'y',
        borderColor: 'rgba(255,59,92,0.95)',
        backgroundColor: 'rgba(255,59,92,0.10)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.18,
        fill: 'origin' as const,
      },
      {
        label: 'Bottom score',
        data: filtered.map(point => point.bottom_score),
        yAxisID: 'y',
        borderColor: 'rgba(0,255,136,0.95)',
        backgroundColor: 'rgba(0,255,136,0.08)',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.18,
        fill: 'origin' as const,
      },
      {
        label: 'BTC',
        data: filtered.map(point => point.price ?? NaN),
        yAxisID: 'y1',
        borderColor: 'rgba(59,130,246,0.70)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
    ],
  }), [filtered]);

  const options = useMemo<ChartOptions<'line'>>(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index' as const, intersect: false },
    plugins: {
      legend: {
        labels: { color: '#9ca3af', font: { size: 12 }, usePointStyle: true, pointStyle: 'line' as const },
      },
      tooltip: {
        backgroundColor: 'rgba(17,24,39,0.95)',
        borderColor: 'rgba(255,255,255,0.08)',
        borderWidth: 1,
        titleColor: '#e8eaed',
        bodyColor: '#9ca3af',
        padding: 12,
        cornerRadius: 10,
        callbacks: {
          title: (items: { dataIndex: number }[]) => fmtDate(filtered[items[0].dataIndex].date),
          afterBody: (items: { dataIndex: number }[]) => {
            const point = filtered[items[0].dataIndex];
            return [
              `Zone: ${zoneLabel(point.cycle_zone)}`,
              `Top: ${(point.top_score * 100).toFixed(1)}%`,
              `Bottom: ${(point.bottom_score * 100).toFixed(1)}%`,
              `Bias: ${point.cycle_bias > 0 ? '+' : ''}${(point.cycle_bias * 100).toFixed(1)}%`,
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
          callback: (value: string | number) => {
            const date = filtered[Number(value)]?.date;
            return date ? date.substring(0, 7) : '';
          },
        },
        grid: { display: false },
      },
      y: {
        position: 'left' as const,
        min: 0,
        max: 1.05,
        ticks: {
          color: '#4b5563',
          font: { family: 'JetBrains Mono', size: 11 },
          callback: (value: string | number) => `${Math.round(Number(value) * 100)}%`,
        },
        grid: { color: 'rgba(255,255,255,0.04)' },
      },
      y1: {
        position: 'right' as const,
        type: 'logarithmic' as const,
        ticks: {
          color: '#4b5563',
          font: { family: 'JetBrains Mono', size: 11 },
          callback: (value: string | number) =>
            '$' + (Number(value) >= 1000 ? `${(Number(value) / 1000).toFixed(0)}k` : value),
        },
        grid: { drawOnChartArea: false },
      },
    },
  }), [filtered]);

  const ranges: Range[] = ['1Y', '2Y', 'ALL'];

  return (
    <div className="chart-box chart-box-lg">
      <div className="chart-header">
        <span className="chart-header-title">Cycle scores & BTC price</span>
        <div className="chart-range-btns">
          {ranges.map(r => (
            <button
              key={r}
              className={`chart-range-btn${r === range ? ' active' : ''}`}
              onClick={() => setRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <Line data={chartData} options={options} plugins={[zonePlugin]} />
    </div>
  );
}
