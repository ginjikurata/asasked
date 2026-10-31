"""Run the sandbox store over HTTP on localhost.

    python scripts/serve_store.py --port 8765

The routes are described in asasked/store/http.py.
"""

from __future__ import annotations

import argparse

from asasked.store.catalog_v1 import CATALOG, CATALOG_VERSION
from asasked.store.http import make_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = make_server(host=args.host, port=args.port)
    print(f"Catalog {CATALOG_VERSION}: {len(CATALOG)} products. "
          f"The store is listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
