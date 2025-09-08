import os
import threading
import runpy
from http.server import HTTPServer, BaseHTTPRequestHandler


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")


def run_http_server() -> None:
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    # Start a minimal HTTP server in the background so Render Web Service detects an open port.
    threading.Thread(target=run_http_server, daemon=True).start()

    # Run the Telegram bot script in the main thread.
    # This executes the top-level code of message_monitor.py as if run directly.
    runpy.run_path("message_monitor.py", run_name="__main__")


