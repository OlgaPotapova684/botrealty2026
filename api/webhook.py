# Vercel serverless function: приём webhook от Telegram
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Корень проекта — bot.py и JSON лежат там
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from telegram import Update
import bot


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b""
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_response(400)
            self.end_headers()
            return

        def run_async():
            # В отдельном потоке свой event loop — избегаем RuntimeError на Vercel
            application = bot.create_application()
            update = Update.de_json(data, application.bot)
            return asyncio.run(application.process_update(update))

        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(run_async).result(timeout=8)
        except Exception as e:
            # Логируем в Vercel (Functions → Logs), чтобы увидеть ошибку
            print("WEBHOOK ERROR:", type(e).__name__, str(e), flush=True)
            import traceback
            traceback.print_exc()

        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass
