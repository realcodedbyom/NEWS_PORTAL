"""
Development runner.

Usage:
    python run.py
"""
import os
from app import create_app

app = create_app(os.getenv("FLASK_CONFIG", "development"))

if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        debug=app.config.get("DEBUG", True),
    )
