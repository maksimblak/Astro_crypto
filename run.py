"""Запуск API и встроенного frontend build: python run.py"""

from research.config import DASHBOARD_HOST, DASHBOARD_PORT

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=True)
