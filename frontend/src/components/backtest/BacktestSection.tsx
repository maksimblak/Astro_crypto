import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api, type BacktestParams } from '../../api/client';
import type { BacktestData } from '../../types/api';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend, Filler);

export default function BacktestSection() {
  const [params, setParams] = useState<BacktestParams>({
    buyThreshold: 1.0,
    sellThreshold: -0.5,
    holdDays: 0,
    positionSize: 1.0,
    useDirection: true,
    sampleSplit: 'test',
  });

  const [shouldFetch, setShouldFetch] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['backtest', params],
    queryFn: () => api.backtest(params),
    enabled: shouldFetch,
    staleTime: 30 * 60 * 1000,
  });

  const handleRun = useCallback(() => {
    setShouldFetch(true);
  }, []);

  const toneClass = (val: number) => (val > 0 ? 'bull' : val < 0 ? 'bear' : 'neutral');

  return (
    <section className="card">
      <h2>Backtesting</h2>
      <p className="card-subtitle">
        Проверка стратегии на исторических данных по астро-скору
      </p>

      <div className="backtest-controls" style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', margin: '1rem 0' }}>
        <label>
          Buy ≥
          <input
            type="number"
            step="0.1"
            value={params.buyThreshold}
            onChange={(e) => {
              setParams({ ...params, buyThreshold: parseFloat(e.target.value) });
              setShouldFetch(false);
            }}
            style={{ width: '5rem', marginLeft: '0.5rem' }}
          />
        </label>
        <label>
          Sell ≤
          <input
            type="number"
            step="0.1"
            value={params.sellThreshold}
            onChange={(e) => {
              setParams({ ...params, sellThreshold: parseFloat(e.target.value) });
              setShouldFetch(false);
            }}
            style={{ width: '5rem', marginLeft: '0.5rem' }}
          />
        </label>
        <label>
          Hold дней
          <input
            type="number"
            min="0"
            value={params.holdDays}
            onChange={(e) => {
              setParams({ ...params, holdDays: parseInt(e.target.value) || 0 });
              setShouldFetch(false);
            }}
            style={{ width: '4rem', marginLeft: '0.5rem' }}
          />
        </label>
        <label>
          Размер позиции
          <input
            type="number"
            min="0.1"
            max="1.0"
            step="0.1"
            value={params.positionSize}
            onChange={(e) => {
              setParams({ ...params, positionSize: parseFloat(e.target.value) });
              setShouldFetch(false);
            }}
            style={{ width: '4rem', marginLeft: '0.5rem' }}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={params.useDirection}
            onChange={(e) => {
              setParams({ ...params, useDirection: e.target.checked });
              setShouldFetch(false);
            }}
          />
          {' '}Direction filter
        </label>
        <label>
          Split
          <select
            value={params.sampleSplit}
            onChange={(e) => {
              setParams({ ...params, sampleSplit: e.target.value });
              setShouldFetch(false);
            }}
            style={{ marginLeft: '0.5rem' }}
          >
            <option value="test">Holdout (test)</option>
            <option value="train">In-sample (train)</option>
            <option value="all">All</option>
          </select>
        </label>
        <button onClick={handleRun} disabled={isLoading}>
          {isLoading ? 'Считаем...' : 'Запустить'}
        </button>
      </div>

      {error && <div className="error">Ошибка: {String(error)}</div>}

      {data && <BacktestResults data={data} />}
    </section>
  );
}

function BacktestResults({ data }: { data: BacktestData }) {
  const alpha = data.total_return_pct - data.buy_hold_return_pct;
  const toneClass = (val: number) => (val > 0 ? 'tone-bull' : val < 0 ? 'tone-bear' : 'tone-neutral');

  const chartData = {
    labels: data.equity_curve.map((p) => p.date),
    datasets: [
      {
        label: 'Strategy equity ($)',
        data: data.equity_curve.map((p) => p.equity),
        borderColor: 'rgba(59, 130, 246, 1)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        fill: true,
        pointRadius: 0,
        borderWidth: 1.5,
      },
      {
        label: 'Buy & Hold ($)',
        data: data.equity_curve.map((p) => (p.close / data.equity_curve[0].close) * 10000),
        borderColor: 'rgba(156, 163, 175, 0.6)',
        backgroundColor: 'transparent',
        pointRadius: 0,
        borderWidth: 1,
        borderDash: [4, 2],
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    plugins: { legend: { display: true, position: 'top' as const } },
    scales: {
      x: { display: false },
      y: { beginAtZero: false },
    },
  };

  return (
    <div>
      <div className="backtest-summary" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', margin: '1rem 0' }}>
        <div className="metric-card">
          <div className="metric-label">Strategy</div>
          <div className={`metric-value ${toneClass(data.total_return_pct)}`}>
            {data.total_return_pct > 0 ? '+' : ''}{data.total_return_pct}%
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Buy & Hold</div>
          <div className={`metric-value ${toneClass(data.buy_hold_return_pct)}`}>
            {data.buy_hold_return_pct > 0 ? '+' : ''}{data.buy_hold_return_pct}%
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Alpha</div>
          <div className={`metric-value ${toneClass(alpha)}`}>
            {alpha > 0 ? '+' : ''}{alpha.toFixed(2)}%
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Sharpe</div>
          <div className="metric-value">{data.sharpe_ratio ?? '—'}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Max DD</div>
          <div className="metric-value tone-bear">{data.max_drawdown_pct}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Win Rate</div>
          <div className="metric-value">{data.win_rate}%</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Trades</div>
          <div className="metric-value">{data.total_trades}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg PnL</div>
          <div className={`metric-value ${toneClass(data.avg_trade_pnl_pct)}`}>
            {data.avg_trade_pnl_pct > 0 ? '+' : ''}{data.avg_trade_pnl_pct}%
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Exposure</div>
          <div className="metric-value">{data.exposure_pct}%</div>
        </div>
      </div>

      <div className="backtest-chart" style={{ margin: '1rem 0' }}>
        <Line data={chartData} options={chartOptions} />
      </div>

      <details style={{ marginTop: '1rem' }}>
        <summary>Сделки ({data.total_trades})</summary>
        <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
          <table className="data-table" style={{ fontSize: '0.8rem' }}>
            <thead>
              <tr>
                <th>Вход</th>
                <th>Цена</th>
                <th>Score</th>
                <th>Выход</th>
                <th>Цена</th>
                <th>Score</th>
                <th>PnL</th>
                <th>Дней</th>
              </tr>
            </thead>
            <tbody>
              {data.trades.map((t, i) => (
                <tr key={i}>
                  <td>{t.entry_date}</td>
                  <td>${t.entry_price.toLocaleString()}</td>
                  <td>{t.entry_score}</td>
                  <td>{t.exit_date}</td>
                  <td>${t.exit_price.toLocaleString()}</td>
                  <td>{t.exit_score}</td>
                  <td className={t.pnl_pct > 0 ? 'tone-bull' : 'tone-bear'}>
                    {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct}%
                  </td>
                  <td>{t.hold_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.5rem' }}>
        Период: {data.period_start} — {data.period_end} ({data.total_days} дней)
      </p>
    </div>
  );
}
