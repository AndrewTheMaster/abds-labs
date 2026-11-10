#!/usr/bin/env python3
"""HTTP transport for the Energosbyt service."""

import json
import os
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .clickhouse_client import ClickHouseClient
from .repository import EnergosbytRepository
from .service import BadRequest, EnergosbytService, NotFound


class Handler(BaseHTTPRequestHandler):
    server_version = "EnergosbytAPI/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_empty(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_error_json(self, status, message):
        self.send_json(status, {"message": message})

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        if not raw:
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def handle_request(self, action):
        try:
            action()
        except BadRequest as error:
            self.send_error_json(400, str(error))
        except NotFound:
            self.send_error_json(404, "Not found")
        except Exception as error:
            self.send_error_json(500, str(error))

    def do_GET(self):
        self.handle_request(self.get)

    def do_POST(self):
        self.handle_request(self.post)

    def do_PATCH(self):
        self.handle_request(self.patch)

    def route(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        return path, params

    def get(self):
        path, params = self.route()
        if path == "/ping":
            self.send_empty(200)
            return
        if path == "/tariffs":
            self.send_json(200, self.server.service.get_tariff(params))
            return
        match = re.fullmatch(r"/users/(\d+)", path)
        if match:
            self.send_json(200, self.server.service.get_user(int(match.group(1))))
            return
        match = re.fullmatch(r"/realty/(\d+)", path)
        if match:
            self.send_json(200, self.server.service.get_realty(int(match.group(1))))
            return
        match = re.fullmatch(r"/realty/(\d+)/readings", path)
        if match:
            self.send_json(200, self.server.service.get_readings(int(match.group(1)), params))
            return
        match = re.fullmatch(r"/realty/(\d+)/invoices", path)
        if match:
            self.send_json(200, self.server.service.get_invoices(int(match.group(1)), params))
            return
        raise NotFound()

    def post(self):
        path, _ = self.route()
        match = re.fullmatch(r"/realty/(\d+)/readings", path)
        if match:
            self.server.service.post_reading(int(match.group(1)), self.read_json())
            self.send_empty(201)
            return
        match = re.fullmatch(r"/realty/(\d+)/gauges", path)
        if match:
            self.server.service.post_gauge(int(match.group(1)), self.read_json())
            self.send_empty(201)
            return
        raise NotFound()

    def patch(self):
        path, _ = self.route()
        match = re.fullmatch(r"/users/(\d+)", path)
        if match:
            self.server.service.patch_user(int(match.group(1)), self.read_json())
            self.send_empty(204)
            return
        raise NotFound()


def main():
    port = int(os.environ["APP_PORT"])
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.service = EnergosbytService(EnergosbytRepository(ClickHouseClient()))
    print(f"Energosbyt API listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
