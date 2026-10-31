"""Окно «свой запрос» по HTTP на localhost — за ним маршрут сайта /api/try.

    python scripts/serve_live.py --port 3005

Описание — в asasked/live.py. Нужны ключи моделей из .env: агент
(OPENAI_COMPAT_*) и страж (LLM_AGREE_PROVIDERS).
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
    print(f"Агент {LIVE_AGENT}; лимиты: {PER_VISITOR} на посетителя, {DAILY_CAP} в сутки. "
          f"Слушает http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
