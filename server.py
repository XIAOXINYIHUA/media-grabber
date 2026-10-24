# -*- coding: utf-8 -*-
"""
MediaGrabber 2.0 網頁版 —— 影音爬取工具
- 純 Python 標準庫 HTTP 服務，瀏覽器訪問 http://127.0.0.1:8765
- 下載引擎共用 grabber_core（與桌面版同一套邏輯）
- 啟動: python server.py          （自動打開瀏覽器）
        python server.py --no-open（不自動打開）
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import grabber_core as core
from grabber_core import (
    VERSION, FORMAT_MAP, COOKIE_BROWSERS,
    DEFAULT_OUT, FFMPEG_PATH,
    load_history, save_history, HISTORY,
)

BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "index.html"


def status_snapshot():
    with core._LOCK:
        tasks = sorted(core.TASKS.values(), key=lambda t: t["created"], reverse=True)
        return [{k: v for k, v in t.items() if k != "_proc"} for t in tasks]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body = INDEX_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/config":
            self._send_json({
                "version": VERSION,
                "outdir": str(DEFAULT_OUT),
                "formats": [{"id": fid, "label": f["label"], "kind": f["kind"]}
                            for fid, f in FORMAT_MAP.items()],
                "cookies": [{"id": cid, "label": label} for label, cid in COOKIE_BROWSERS],
                "has_ffmpeg": bool(FFMPEG_PATH),
                "ytdlp_version": core.ytdlp_version(),
            })
        elif path == "/api/status":
            self._send_json({"tasks": status_snapshot()})
        elif path == "/api/history":
            with core._LOCK:
                self._send_json({"history": list(HISTORY)})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        data = self._body()
        try:
            if path == "/api/info":
                url = (data.get("url") or "").strip()
                if not url:
                    raise RuntimeError("請先填寫連結")
                self._send_json(core.fetch_info(url, data.get("cookie") or ""))
            elif path == "/api/download":
                urls = [u.strip() for u in (data.get("urls") or []) if u.strip()]
                if not urls:
                    raise RuntimeError("請先填寫連結")
                fmt = data.get("format") or "mp3"
                if fmt not in FORMAT_MAP:
                    raise RuntimeError("不支援的格式: %s" % fmt)
                outdir = (data.get("outdir") or "").strip() or str(DEFAULT_OUT)
                outdir = str(Path(os.path.expanduser(outdir)).resolve())
                tid = core.create_task(urls, fmt, outdir, data.get("cookie") or "")
                self._send_json({"task_id": tid})
            elif path == "/api/cancel":
                ok = core.cancel_task(data.get("id") or "")
                self._send_json({"ok": ok})
            elif path == "/api/open":
                p = (data.get("path") or "").strip()
                if not p:
                    raise RuntimeError("缺少路徑")
                pp = Path(p)
                if pp.is_dir():
                    os.startfile(str(pp))  # noqa
                elif pp.exists():
                    subprocess.Popen('explorer /select,"%s"' % pp, shell=True)
                else:
                    raise RuntimeError("路徑不存在")
                self._send_json({"ok": True})
            elif path == "/api/history/clear":
                with core._LOCK:
                    HISTORY.clear()
                    save_history()
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)
        except subprocess.TimeoutExpired:
            self._send_json({"error": "取得資訊逾時，請檢查連結或網路"}, 500)
        except RuntimeError as e:
            self._send_json({"error": str(e)}, 400)
        except Exception as e:
            self._send_json({"error": "伺服器錯誤: %s" % e}, 500)


def main():
    load_history()
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)

    server = None
    port = 8765
    for p in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if server is None:
        print("錯誤: 8765-8775 埠均被佔用")
        sys.exit(1)

    print("=" * 52)
    print("  MediaGrabber v%s 影音爬取工具（網頁版）" % VERSION)
    print("  地址: http://127.0.0.1:%d" % port)
    print("  yt-dlp: %s" % " ".join(core.YTDLP_CMD))
    print("  ffmpeg: %s" % (FFMPEG_PATH or "未找到（影片功能不可用）"))
    print("  預設保存目錄: %s" % DEFAULT_OUT)
    print("=" * 52)
    print("按 Ctrl+C 停止服務")

    if "--no-open" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:%d" % port)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
