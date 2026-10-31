"""An HTTP wrapper around the sandbox store, for agents that do not live in
this process (their own framework, another language).

    GET  /tools                          tool descriptions
    POST /sessions                       {"mandate": {...}, "user_reply": "..."}
                                         -> {"session_id": ..., "tools": [...]}
    POST /sessions/<id>/call             {"tool": "search_products", "args": {...}}
                                         -> the tool's result
    GET  /sessions/<id>/transcript       the call log and the final order

Standard library only. Listens on localhost: this is a sandbox for runs, not
a public service.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .store import TOOLS, Mandate, Store

_SESSION_CALL = re.compile(r"^/sessions/([\w-]+)/call$")
_SESSION_LOG = re.compile(r"^/sessions/([\w-]+)/transcript$")


def _mandate(data: dict) -> Mandate:
    try:
        return Mandate(
            prompt_summary=str(data["prompt_summary"]),
            allowlist=tuple(data["allowlist"]),
            quantity_cap=int(data["quantity_cap"]),
            amount_min_cents=int(data["amount_min_cents"]),
            amount_max_cents=int(data["amount_max_cents"]),
            **({"allowed_merchants": tuple(data["allowed_merchants"])}
               if "allowed_merchants" in data else {}),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"bad mandate: {e}") from e


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("body must be a JSON object")
            return data

        def _session(self, sid: str):
            session = store.sessions.get(sid)
            if session is None:
                self._send(404, {"error": f"no session {sid}"})
            return session

        def do_GET(self):  # noqa: N802
            if self.path == "/tools":
                return self._send(200, TOOLS)
            if m := _SESSION_LOG.match(self.path):
                if session := self._session(m.group(1)):
                    order = session.order
                    return self._send(200, {
                        "session_id": session.session_id,
                        "transcript": session.transcript,
                        "questions": session.questions,
                        "order": None if order is None else {
                            "order_id": order.order_id, "placed": order.placed,
                            "purchase": order.purchase, "total_cents": order.total_cents,
                            "merchant_id": order.merchant_id,
                            "vi": {k: order.vi[k] for k in
                                   ("chain_valid", "constraints_ok", "violations")},
                        },
                    })
                return None
            return self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            try:
                data = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": str(e)})
            if self.path == "/sessions":
                try:
                    session = store.new_session(_mandate(data.get("mandate") or {}),
                                                data.get("user_reply"))
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(201, {"session_id": session.session_id, "tools": TOOLS})
            if m := _SESSION_CALL.match(self.path):
                if session := self._session(m.group(1)):
                    args = data.get("args") or {}
                    if not isinstance(args, dict):
                        return self._send(400, {"error": "args must be an object"})
                    return self._send(200, session.call(str(data.get("tool")), args))
                return None
            return self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):  # quiet: the session keeps its own log
            pass

    return Handler


def make_server(store: Store | None = None, host: str = "127.0.0.1", port: int = 8765):
    return ThreadingHTTPServer((host, port), make_handler(store or Store()))
