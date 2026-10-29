"""Optional loopback-only preview API, outside the production application."""

import argparse
import gzip
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from build_r11_r10_reverse_sizing_review import guarded_reexec, sources

from cold_storage.modules.layout.application.room_reverse_sizing_review import (
    preview_request,
    preview_room_sizing,
)
from cold_storage.modules.layout.infrastructure.room_reverse_sizing_page import plot_record


def preview_handler(root: Path, review: Path) -> type[BaseHTTPRequestHandler]:
    catalog, r7, r8, _ = sources(root)
    evidence: dict[str, bytes] = {}

    class Handler(BaseHTTPRequestHandler):
        def send_body(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/":
                self.send_body(
                    200, (review / "index.html").read_bytes(), "text/html; charset=utf-8"
                )
            elif (
                self.path.startswith("/evidence/")
                and unquote(self.path[len("/evidence/") :]) in evidence
            ):
                self.send_body(
                    200, evidence[unquote(self.path[len("/evidence/") :])], "application/gzip"
                )
            elif (
                (name := unquote(self.path[1:]))
                and "/" not in name
                and "\\" not in name
                and (path := review / name).is_file()
                and path.resolve().parent == review.resolve()
            ):
                kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                self.send_body(200, path.read_bytes(), kind)
            else:
                self.send_body(404, b'{"error":"NOT_FOUND"}', "application/json")

        def do_POST(self) -> None:
            if self.path != "/preview":
                self.send_body(404, b"{}", "application/json")
                return
            origin = self.headers.get("Origin")
            if origin is not None and origin != f"http://127.0.0.1:{self.server.server_port}":
                self.send_body(
                    403, b'{"error":"LOCAL_PREVIEW_ORIGIN_REQUIRED"}', "application/json"
                )
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("BOUNDED_PREVIEW_REQUEST_REQUIRED")
                c, search = preview_request(json.loads(self.rfile.read(length)))
                plots = {}
                pending = {}

                def save(case: dict[str, Any]) -> None:
                    key = case["summary"]["id"]
                    plots[key] = plot_record(case)
                    pending[key] = gzip.compress(
                        json.dumps(case, ensure_ascii=False, separators=(",", ":")).encode(),
                        mtime=0,
                    )

                result = preview_room_sizing(catalog, r7, r8, c, search, evidence_sink=save)
                evidence.clear()
                evidence.update(pending)
                self.send_body(
                    200,
                    json.dumps(
                        dict(data=result, plots=plots, evidence_url_prefix="/evidence/"),
                        ensure_ascii=False,
                    ).encode(),
                    "application/json; charset=utf-8",
                )
            except (ValueError, TypeError, KeyError) as exc:
                self.send_body(400, json.dumps(dict(error=str(exc))).encode(), "application/json")

    return Handler


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--review", type=Path, required=True)
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    code = guarded_reexec(args.review.parent / (args.review.name + "-preview-native-guard"))
    if code is not None:
        raise SystemExit(code)
    if not 1024 <= args.port <= 65535:
        raise ValueError("USER_LOOPBACK_PORT_REQUIRED")
    with HTTPServer(
        ("127.0.0.1", args.port),
        preview_handler(Path(__file__).resolve().parents[2], args.review.resolve()),
    ) as server:
        print(f"Functional preview only: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
