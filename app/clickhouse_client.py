"""Small HTTP client for ClickHouse; it knows nothing about the lab tables."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class ClickHouseClient:
    def __init__(self):
        host = os.environ["CLICKHOUSE_HOST"]
        port = os.environ["CLICKHOUSE_HTTP_PORT"]
        self.base_url = f"http://{host}:{port}/"
        self.user = os.environ["CLICKHOUSE_USER"]
        self.password = os.environ["CLICKHOUSE_PASSWORD"]

    def _request(self, query, body=None):
        url = self.base_url + "?" + urllib.parse.urlencode({"query": query})
        headers = {"X-ClickHouse-User": self.user}
        if self.password:
            headers["X-ClickHouse-Key"] = self.password
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
        return json.loads(self._request(query + " FORMAT JSON")).get("data", [])

    def scalar(self, query):
        rows = self.rows(query)
        return list(rows[0].values())[0] if rows else 0

    def insert(self, query, rows):
        body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
        self._request(query, body)

    def execute(self, query):
        self._request(query)
