from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.llm import VertexClient  # noqa: E402


def main() -> int:
    client = VertexClient()
    message = client.ping()
    print(
        f"OK provider={client.provider} project={client.settings.project_id or '-'} "
        f"location={client.settings.location} model={client.last_model} ping={message}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
