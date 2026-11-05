#!/usr/bin/env python3
"""AegisCloud dev server.

    python run.py                # http://0.0.0.0:5000
    AEGIS_PORT=8000 python run.py
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("AEGIS_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("AEGIS_DEBUG", "0") == "1",
            threaded=True, use_reloader=False)
