#!/usr/bin/python3
"""LAN-only reverse proxy to the Flask development server on localhost:8080."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UPSTREAM = "http://127.0.0.1:8080"


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "connection", "content-length"}
        }
        request = Request(
            UPSTREAM + self.path,
            data=body,
            headers=headers,
            method=self.command,
        )
        try:
            response = urlopen(request, timeout=65)
        except HTTPError as error:
            response = error
        except URLError:
            payload = b"Upstream Flask server is unavailable."
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        payload = response.read()
        status = response.getcode()
        self.send_response(status if isinstance(status, int) else 502)
        for key, value in response.headers.items():
            if key.lower() not in {
                "connection",
                "content-length",
                "transfer-encoding",
                "server",
                "date",
            }:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _proxy
    do_POST = _proxy


if __name__ == "__main__":
    print("LAN proxy listening on http://0.0.0.0:8081", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8081), ProxyHandler).serve_forever()
