import { useMemo } from 'react';
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
import type { ChartData, ChartOptions } from 'chart.js';
import type { CycleHistory } from '../../types/api';
import { fmtDate } from '../../utils/dates';

ChartJS.register(CategoryScale, LinearScale, LogarithmicScale, PointElement, LineElement, Tooltip, Legend, Filler);

interface Props {
  history: CycleHistory[];
}

function zoneLabel(zone: string): string {
  if (zone === 'top_zone') return 'Top zone';
  if (zone === 'top_watch') return 'Top watch';
  if (zone === 'bottom_zone') return 'Bottom zone';
  if (zone === 'bottom_watch') return 'Bottom watch';
  if (zone === 'mixed') return 'Mixed';
  return 'Neutral';
}

export default function CycleChart({ history }: Props) {
  const chartData = useMemo<ChartData<'line', number[], string>>(() => ({
    labels: history.map(point => point.date),
    datasets: [
      {
        label: 'Top score',
        data: history.map(point => point.top_score),
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
        data: history.map(point => point.bottom_score),
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
        data: history.map(point => point.price ?? NaN),
        yAxisID: 'y1',
        borderColor: 'rgba(59,130,246,0.70)',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.15,
      },
    ],
  }), [history]);

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
          title: (items: { dataIndex: number }[]) => fmtDate(history[items[0].dataIndex].date),
          afterBody: (items: { dataIndex: number }[]) => {
            const point = history[items[0].dataIndex];
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
            const date = history[Number(value)]?.date;
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
  }), [history]);

  return (
    <div className="chart-box chart-box-lg">
      <Line data={chartData} options={options} />
    </div>
  );
}
