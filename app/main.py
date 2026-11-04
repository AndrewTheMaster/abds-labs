#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "energosbyt")
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_HTTP_PORT = os.environ.get("CLICKHOUSE_HTTP_PORT", "8123")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
APP_PORT = int(os.environ.get("APP_PORT", "8080"))

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ClickHouse:
    def __init__(self):
        self.base_url = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_HTTP_PORT}/"

    def _request(self, query, body=None):
        url = self.base_url + "?" + urllib.parse.urlencode({"query": query})
        headers = {}
        if CLICKHOUSE_USER:
            headers["X-ClickHouse-User"] = CLICKHOUSE_USER
        if CLICKHOUSE_PASSWORD:
            headers["X-ClickHouse-Key"] = CLICKHOUSE_PASSWORD
        data = None
        if body is not None:
            data = body.encode("utf-8")
            headers["Content-Type"] = "text/plain; charset=utf-8"
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise RuntimeError(f"clickhouse: {detail}") from error

    def rows(self, query):
        payload = self._request(query + " FORMAT JSON")
        return json.loads(payload).get("data", [])

    def insert(self, query, rows):
        body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
        self._request(query, body)

    def execute(self, query):
        self._request(query)

    def scalar(self, query):
        rows = self.rows(query)
        if not rows:
            return 0
        return list(rows[0].values())[0]


def is_uint(value, minimum=0, maximum=(1 << 64) - 1):
    return (isinstance(value, int) and not isinstance(value, bool)
            and minimum <= value <= maximum)


def parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        return None


def parse_datetime(value):
    try:
        return datetime.strptime(value, DATETIME_FORMAT)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1)


def text_value(value):
    return isinstance(value, str) and value.strip() != ""


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

    def invalid_field(self, name):
        self.send_error_json(400, f'invalid "{name}" field')

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

    def realty_exists(self, realty_id):
        query = f"SELECT count() AS c FROM {DATABASE}.dim_realty WHERE id = {realty_id}"
        return int(self.server.ch.scalar(query)) > 0

    def do_GET(self):
        try:
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path.rstrip("/") or "/"
            if path == "/ping":
                self.send_empty(200)
                return
            if path == "/tariffs":
                self.get_tariffs(parsed.query)
                return
            match = re.fullmatch(r"/users/(\d+)", path)
            if match:
                self.get_user(int(match.group(1)))
                return
            match = re.fullmatch(r"/realty/(\d+)", path)
            if match:
                self.get_realty(int(match.group(1)))
                return
            match = re.fullmatch(r"/realty/(\d+)/readings", path)
            if match:
                self.get_readings(int(match.group(1)), parsed.query)
                return
            match = re.fullmatch(r"/realty/(\d+)/invoices", path)
            if match:
                self.get_invoices(int(match.group(1)), parsed.query)
                return
            self.send_error_json(404, "Not found")
        except Exception as error:
            self.send_error_json(500, str(error))

    def do_POST(self):
        try:
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path.rstrip("/") or "/"
            match = re.fullmatch(r"/realty/(\d+)/readings", path)
            if match:
                self.post_reading(int(match.group(1)))
                return
            match = re.fullmatch(r"/realty/(\d+)/gauges", path)
            if match:
                self.post_gauge(int(match.group(1)))
                return
            self.send_error_json(404, "Not found")
        except Exception as error:
            self.send_error_json(500, str(error))

    def do_PATCH(self):
        try:
            parsed = urllib.parse.urlsplit(self.path)
            path = parsed.path.rstrip("/") or "/"
            match = re.fullmatch(r"/users/(\d+)", path)
            if match:
                self.patch_user(int(match.group(1)))
                return
            self.send_error_json(404, "Not found")
        except Exception as error:
            self.send_error_json(500, str(error))

    def get_user(self, user_id):
        rows = self.server.ch.rows(
            f"SELECT id, fio, phone, phone_prev FROM {DATABASE}.dim_users FINAL "
            f"WHERE id = {user_id} LIMIT 1"
        )
        if not rows:
            self.send_error_json(404, "Not found")
            return
        row = rows[0]
        self.send_json(200, {
            "id": int(row["id"]),
            "fio": row["fio"],
            "phone": row["phone"],
            "phone_prev": row["phone_prev"],
        })

    def patch_user(self, user_id):
        body = self.read_json()
        if body is None:
            self.send_error_json(400, "invalid request body")
            return
        has_fio = "fio" in body
        has_phone = "phone" in body
        if has_fio and not text_value(body["fio"]):
            self.invalid_field("fio")
            return
        if has_phone and not text_value(body["phone"]):
            self.invalid_field("phone")
            return
        if not has_fio and not has_phone:
            self.send_error_json(400, "at least one field is required")
            return
        rows = self.server.ch.rows(
            f"SELECT id, fio, phone, phone_prev, created_at, updated_at "
            f"FROM {DATABASE}.dim_users FINAL WHERE id = {user_id} LIMIT 1"
        )
        if not rows:
            self.send_error_json(404, "Not found")
            return
        current = rows[0]
        new_phone = current["phone"]
        new_phone_prev = current["phone_prev"]
        if has_phone:
            new_phone = body["phone"]
            if new_phone != current["phone"]:
                new_phone_prev = current["phone"]
        updated_at = datetime.utcnow().replace(microsecond=0)
        previous_updated_at = parse_datetime(current["updated_at"])
        if updated_at <= previous_updated_at:
            updated_at = previous_updated_at + timedelta(seconds=1)
        row = {
            "id": user_id,
            "fio": body["fio"] if has_fio else current["fio"],
            "phone": new_phone,
            "phone_prev": new_phone_prev,
            "created_at": current["created_at"],
            "updated_at": updated_at.strftime(DATETIME_FORMAT),
        }
        if has_fio and body["fio"] != current["fio"]:
            encoded_fio = body["fio"].encode("utf-8").hex()
            self.server.ch.execute(
                f"ALTER TABLE {DATABASE}.dim_users UPDATE fio = unhex('{encoded_fio}') "
                f"WHERE id = {user_id} SETTINGS mutations_sync = 1"
            )
        self.server.ch.insert(
            f"INSERT INTO {DATABASE}.dim_users FORMAT JSONEachRow",
            [row],
        )
        self.send_empty(204)

    def get_realty(self, realty_id):
        rows = self.server.ch.rows(
            f"SELECT id, address, square, type, number, rooms, floor, porch "
            f"FROM {DATABASE}.dim_realty WHERE id = {realty_id} LIMIT 1"
        )
        if not rows:
            self.send_error_json(404, "Not found")
            return
        row = rows[0]
        self.send_json(200, {
            "id": int(row["id"]),
            "address": row["address"],
            "square": int(row["square"]),
            "type": row["type"],
            "number": row["number"],
            "rooms": int(row["rooms"]),
            "floor": int(row["floor"]),
            "porch": int(row["porch"]),
        })

    def post_reading(self, realty_id):
        body = self.read_json()
        if body is None:
            self.send_error_json(400, "invalid request body")
            return
        for field in ("user_id", "gauge_id", "tariff_id"):
            if field not in body or not is_uint(body[field], 1):
                self.invalid_field(field)
                return
        reading_date = parse_date(body.get("reading_date"))
        if reading_date is None:
            self.invalid_field("reading_date")
            return
        for field in ("day_kw", "night_kw"):
            if field not in body or not is_uint(body[field], 0, (1 << 32) - 1):
                self.invalid_field(field)
                return
        user_id = body["user_id"]
        gauge_id = body["gauge_id"]
        tariff_id = body["tariff_id"]
        if not self.realty_exists(realty_id):
            self.send_error_json(404, "Not found")
            return
        checks = [
            (f"SELECT count() AS c FROM {DATABASE}.dim_users FINAL WHERE id = {user_id}"),
            (f"SELECT count() AS c FROM {DATABASE}.dim_gauges WHERE id = {gauge_id}"),
            (f"SELECT count() AS c FROM {DATABASE}.dim_tariffs FINAL WHERE id = {tariff_id}"),
        ]
        if any(int(self.server.ch.scalar(query)) == 0 for query in checks):
            self.send_error_json(404, "Not found")
            return
        day = reading_date.isoformat()
        created_at = datetime.utcnow().replace(microsecond=0)
        rows = self.server.ch.rows(
            f"SELECT max(created_at) AS m FROM {DATABASE}.fact_meter_readings "
            f"WHERE realty_id = {realty_id} AND reading_date = toDate('{day}')"
        )
        if rows:
            latest = parse_datetime(rows[0]["m"])
            if created_at <= latest:
                created_at = latest + timedelta(seconds=1)
        self.server.ch.insert(
            f"INSERT INTO {DATABASE}.fact_meter_readings FORMAT JSONEachRow",
            [{
                "realty_id": realty_id,
                "user_id": user_id,
                "tariff_id": tariff_id,
                "gauge_id": gauge_id,
                "reading_date": day,
                "day_kw": body["day_kw"],
                "night_kw": body["night_kw"],
                "created_at": created_at.strftime(DATETIME_FORMAT),
            }],
        )
        self.send_empty(201)

    def get_readings(self, realty_id, query):
        params = urllib.parse.parse_qs(query, keep_blank_values=True)
        date_from = parse_date(params.get("date_from", [None])[0])
        date_to = parse_date(params.get("date_to", [None])[0])
        if date_from is None:
            self.send_error_json(400, 'invalid "date_from" parameter')
            return
        if date_to is None:
            self.send_error_json(400, 'invalid "date_to" parameter')
            return
        if date_from > date_to:
            self.send_error_json(400, 'invalid "date_from" parameter')
            return
        if not self.realty_exists(realty_id):
            self.send_error_json(404, "Not found")
            return
        rows = self.server.ch.rows(
            f"SELECT realty_id, user_id, tariff_id, gauge_id, reading_date, day_kw, night_kw "
            f"FROM {DATABASE}.fact_meter_readings FINAL "
            f"WHERE realty_id = {realty_id} "
            f"AND reading_date >= toDate('{date_from.isoformat()}') "
            f"AND reading_date <= toDate('{date_to.isoformat()}') "
            f"ORDER BY reading_date"
        )
        readings = [{
            "reading_date": row["reading_date"],
            "user_id": int(row["user_id"]),
            "tariff_id": int(row["tariff_id"]),
            "gauge_id": int(row["gauge_id"]),
            "day_kw": int(row["day_kw"]),
            "night_kw": int(row["night_kw"]),
        } for row in rows]
        self.send_json(200, {"readings": readings, "count": len(readings)})

    def get_invoices(self, realty_id, query):
        params = urllib.parse.parse_qs(query, keep_blank_values=True)
        values = {}
        for name, default in (("limit", 10), ("offset", 0)):
            if name not in params:
                values[name] = default
                continue
            raw = params[name][0]
            if not re.fullmatch(r"\d+", raw or ""):
                self.send_error_json(400, f'invalid "{name}" parameter')
                return
            values[name] = int(raw)
        if not self.realty_exists(realty_id):
            self.send_error_json(404, "Not found")
            return
        total = int(self.server.ch.scalar(
            f"SELECT count() AS c FROM {DATABASE}.fact_invoice WHERE realty_id = {realty_id}"
        ))
        rows = self.server.ch.rows(
            f"SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at "
            f"FROM {DATABASE}.fact_invoice WHERE realty_id = {realty_id} "
            f"ORDER BY created_at DESC LIMIT {values['limit']} OFFSET {values['offset']}"
        )
        invoices = [{
            "tariff_id": int(row["tariff_id"]),
            "gauge_id": int(row["gauge_id"]),
            "day_kw": int(row["day_kw"]),
            "night_kw": int(row["night_kw"]),
            "price": int(row["price"]),
            "deadline": row["deadline"],
            "created_at": row["created_at"],
        } for row in rows]
        self.send_json(200, {"invoices": invoices, "count": total})

    def get_tariffs(self, query):
        params = urllib.parse.parse_qs(query, keep_blank_values=True)
        day = parse_date(params.get("date", [None])[0])
        if day is None:
            self.send_error_json(400, 'invalid "date" parameter')
            return
        timestamp = day.isoformat() + " 00:00:00"
        rows = self.server.ch.rows(
            f"SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to "
            f"FROM {DATABASE}.dim_tariffs FINAL "
            f"WHERE valid_from <= toDateTime('{timestamp}') "
            f"AND valid_to > toDateTime('{timestamp}') "
            f"ORDER BY id LIMIT 1"
        )
        if not rows:
            self.send_error_json(404, "Not found")
            return
        row = rows[0]
        self.send_json(200, {
            "id": int(row["id"]),
            "name": row["name"],
            "price_day_kwph": int(row["price_day_kwph"]),
            "price_night_kwph": int(row["price_night_kwph"]),
            "valid_from": row["valid_from"],
            "valid_to": row["valid_to"],
        })

    def post_gauge(self, realty_id):
        body = self.read_json()
        if body is None:
            self.send_error_json(400, "invalid request body")
            return
        gauge_id = body.get("gauge_id")
        if not is_uint(gauge_id, 1):
            self.invalid_field("gauge_id")
            return
        if not self.realty_exists(realty_id):
            self.send_error_json(404, "Not found")
            return
        gauge_count = int(self.server.ch.scalar(
            f"SELECT count() AS c FROM {DATABASE}.dim_gauges WHERE id = {gauge_id}"
        ))
        if gauge_count == 0:
            self.send_error_json(404, "Not found")
            return
        active = self.server.ch.rows(
            f"SELECT gauge_id, version FROM {DATABASE}.fact_gauge_bindings FINAL "
            f"WHERE realty_id = {realty_id} AND sign = 1 "
            f"ORDER BY version DESC LIMIT 1"
        )
        created_at = datetime.utcnow().replace(microsecond=0).strftime(DATETIME_FORMAT)
        rows = []
        if active:
            old_gauge = int(active[0]["gauge_id"])
            old_version = int(active[0]["version"])
            rows.append({
                "gauge_id": old_gauge,
                "realty_id": realty_id,
                "created_at": created_at,
                "sign": -1,
                "version": old_version,
            })
            version = old_version + 1
        else:
            version = 1
        rows.append({
            "gauge_id": gauge_id,
            "realty_id": realty_id,
            "created_at": created_at,
            "sign": 1,
            "version": version,
        })
        self.server.ch.insert(
            f"INSERT INTO {DATABASE}.fact_gauge_bindings FORMAT JSONEachRow",
            rows,
        )
        self.send_empty(201)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", APP_PORT), Handler)
    server.ch = ClickHouse()
    print(f"Energosbyt API listening on 0.0.0.0:{APP_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
