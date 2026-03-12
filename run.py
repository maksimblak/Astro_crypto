"""
Запуск дашборда:
  FastAPI (новый): python run.py
  Flask (старый):  python run.py --flask
"""

import sys

if __name__ == "__main__":
    if "--flask" in sys.argv:
        import os

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dashboard"))
        from dashboard import app, start_auto_updater

        start_auto_updater()
        app.run(host="0.0.0.0", port=5000)
    else:
        import uvicorn

        uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=True)
