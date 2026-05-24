#!/usr/bin/env python3

import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    uvicorn.run("web.editor_service:app", host="0.0.0.0", port=3002, reload=False)
