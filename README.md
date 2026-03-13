# Crypto Ideas

Исследовательский проект по BTC с тремя основными слоями:

- `research/` — загрузка рыночных данных, расчёт признаков, astro- и market-backtests;
- `backend/` — FastAPI API поверх подготовленной DuckDB-базы;
- `frontend/` — React/Vite dashboard, который можно собрать и раздавать через backend.

Основная база проекта: `data/btc_research.duckdb`.

## Структура

- `research/` — data pipeline, astro scoring, feature engineering, backtests.
- `backend/` — FastAPI routers и доступ к DuckDB.
- `dashboard/` — расчёт market regime и автообновление пайплайна.
- `frontend/` — SPA-интерфейс для календаря, режима и статистики.
- `data/` — DuckDB, логи автообновления, CSV-артефакты.
- `charts/` — сохранённые графики исследований.
- `run.py` — локальный запуск API на Uvicorn.

## Требования

- Python 3.12+
- Node.js 20.19+ или 22.12+ для сборки frontend через Vite 7
- доступ в интернет для `yfinance` и внешних API, если обновляются market features

Астро-часть использует Skyfield и файл эфемерид `de421.bsp`. Проект ищет его в `data/de421.bsp` и в корне репозитория. Если локального файла нет, Skyfield попробует скачать его автоматически.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Для frontend:

```bash
cd frontend
npm install
```

## Быстрый старт

1. Обновить рыночные данные и pivots:

```bash
python3 research/main.py
```

2. Построить astro scoring и расширенные pivot-профили:

```bash
python3 research/astro_scoring.py
python3 research/astro_extended_analysis.py
```

3. Если нужен frontend через backend, собрать его:

```bash
cd frontend
npm run build
cd ..
```

4. Запустить API:

```bash
python3 run.py
```

5. Открыть backend со встроенным production-build frontend:

```text
http://127.0.0.1:8000
```

Если `frontend/dist` не собран, backend поднимет только API. Для отдельной frontend-разработки:

```bash
cd frontend
npm run dev
```

Vite dev server проксирует `/api` на `http://localhost:8000`.

## Полезные команды

Обновить только market features и derivatives history:

```bash
python3 research/market_features.py
```

Backtest market features:

```bash
python3 research/backtest_market_features.py
```

Natal-transit анализ:

```bash
python3 research/astro_natal_transits_test.py --start 2016-01-01 --orb 3
```

Собрать frontend:

```bash
cd frontend
npm run build
```

## Основные зависимости

- `fastapi`
- `uvicorn`
- `duckdb`
- `numpy`
- `pandas`
- `scipy`
- `skyfield`
- `requests`
- `yfinance`
- `react`
- `vite`

## Архитектурные замечания

- Data pipeline и dashboard используют одну DuckDB-базу как общий источник данных.
- `dashboard/auto_update.py` может автоматически прогонять pipeline по расписанию.
- Астро-результаты и market regime являются исследовательскими метриками, а не торговыми рекомендациями.
