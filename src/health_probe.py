"""Docker/process health probe. Exits 0 when /health responds."""

from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    port = os.environ.get("PORT", "8080")
    path = os.environ.get("HEALTHCHECK_PATH", "/health")
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status != 200:
                return 1
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
