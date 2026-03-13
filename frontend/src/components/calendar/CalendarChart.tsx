import { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, BarElement,
  Tooltip, Legend,
} from 'chart.js';
import type { CalendarDay, ScoreScale } from '../../types/api';
import { fmtShort, fmtDate } from '../../utils/dates';
import { scoreBarColor, scoreBarBorder } from '../../utils/scores';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

interface Props {
  data: CalendarDay[];
  scoreScale: ScoreScale;
}

export default function CalendarChart({ data, scoreScale }: Props) {
  const chartData = useMemo(() => {
    const scores = data.map(d => d.score);
    return {
      labels: data.map(d => fmtShort(d.date)),
      datasets: [{
        data: scores,
        backgroundColor: scores.map(s => scoreBarColor(s, scoreScale)),
        borderColor: scores.map(s => scoreBarBorder(s, scoreScale)),
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false as const,
      }],
    };
  }, [data, scoreScale]);

  const options = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(17,24,39,0.95)',
        borderColor: 'rgba(0,212,255,0.2)',
        borderWidth: 1,
        titleColor: '#e8eaed',
        bodyColor: '#9ca3af',
        titleFont: { size: 13, weight: 600 as const },
        bodyFont: { size: 12, family: 'JetBrains Mono' },
        padding: 14,
        cornerRadius: 10,
        callbacks: {
          title: (items: { dataIndex: number }[]) => fmtDate(data[items[0].dataIndex].date),
          afterTitle: (items: { dataIndex: number }[]) => {
            const d = data[items[0].dataIndex];
            return `${d.quarter} | \u263D ${d.moon_sign} (${d.moon_element}) | \u2609 ${d.sun_sign || '\u2014'}`;
          },
          label: (item: { raw: unknown }) => `Балл: ${(item.raw as number).toFixed(1)}`,
          afterBody: (items: { dataIndex: number }[]) => {
            const d = data[items[0].dataIndex];
            if (!d.details) return '';
            return '\n' + d.details.split(' | ').join('\n');
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#4b5563', maxRotation: 90, font: { size: data.length > 60 ? 7 : 10 } },
        grid: { display: false },
      },
      y: {
        ticks: { color: '#4b5563', font: { family: 'JetBrains Mono', size: 11 } },
        grid: { color: 'rgba(255,255,255,0.04)' },
        beginAtZero: true,
      },
    },
  }), [data]);

  return (
    <div className="chart-box chart-box-lg">
      <Bar data={chartData} options={options} />
    </div>
  );
}
