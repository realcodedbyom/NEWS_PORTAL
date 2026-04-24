"""
WSGI entrypoint for production servers (gunicorn/uwsgi).

Usage:
    gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Convenience for `python wsgi.py`
    app.run(host="0.0.0.0", port=8000, debug=app.config.get("DEBUG", False))
