"""The "your own request" window over HTTP on localhost, behind the site's /api/try route.

    python scripts/serve_live.py --port 3005

Described in asasked/live.py. Needs model keys from .env: the agent
(OPENAI_COMPAT_*) and the guard (LLM_AGREE_PROVIDERS).
"""

from __future__ import annotations

import argparse

from asasked.live import DAILY_CAP, LIVE_AGENT, PER_VISITOR, make_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3005)
    args = parser.parse_args()

    server = make_server(host=args.host, port=args.port)
    print(f"Agent {LIVE_AGENT}; limits: {PER_VISITOR} per visitor, {DAILY_CAP} per day. "
          f"Listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
