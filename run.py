"""
Запуск дашборда: python run.py
Откроет http://localhost:5000
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "dashboard"))

from dashboard import app, start_auto_updater

if __name__ == "__main__":
    start_auto_updater()
    app.run(host="0.0.0.0", port=5000)
