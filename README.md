# Crypto Ideas

Исследовательский проект по BTC с двумя основными направлениями:

- сбор и нормализация исторических рыночных данных в SQLite;
- исследовательские модели и астрологические/рыночные backtest-скрипты;
- локальный Flask-дашборд поверх подготовленной базы.

Проект хранит данные в `data/btc_research.db` и использует набор standalone-скриптов из `research/` для обновления таблиц и построения аналитики.

## Структура

- `research/` — подготовка данных, backtests, астрологические исследования, расчет признаков.
- `dashboard/` — Flask backend и HTML-шаблон дашборда.
- `data/` — SQLite база, CSV и служебные артефакты обновления.
- `charts/` — сохраненные графики.
- `run.py` — локальный запуск дашборда.

## Требования

- Python 3.12+
- SQLite
- доступ в интернет для `yfinance` и внешних API, если обновляются market features

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Если editable-установка не нужна:

```bash
pip install .
```

## Быстрый старт

1. Инициализировать и обновить базу:

```bash
python3 research/main.py
```

2. Запустить дашборд:

```bash
python3 run.py
```

3. Открыть:

```text
http://localhost:5000
```

## Полезные команды

Обновить pivots и market features:

```bash
python3 research/main.py
```

Запустить natal-transit анализ:

```bash
python3 research/astro_natal_transits_test.py --start 2016-01-01 --orb 3
```

Backtest market features:

```bash
python3 research/backtest_market_features.py
```

## Зависимости

Основные библиотеки проекта:

- `Flask`
- `matplotlib`
- `numpy`
- `pandas`
- `PyEphem`
- `requests`
- `scipy`
- `yfinance`

## Замечания по текущей архитектуре

- Проект пока ориентирован на запуск скриптов напрямую из `research/`.
- База данных является центральным слоем обмена между research-скриптами и дашбордом.
- Многие исследования ретроспективные: результаты не стоит трактовать как real-time сигналы без отдельной out-of-sample проверки.

## Следующий разумный шаг

Если проект будет развиваться дальше, имеет смысл:

- превратить `research/` и `dashboard/` в полноценные пакеты;
- добавить автотесты для data pipeline и статистических функций;
- фиксировать версии экспериментов и параметры прогонов в БД.
