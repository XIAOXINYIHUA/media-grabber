# -*- coding: utf-8 -*-
"""
grabber_core —— MediaGrabber 共用核心模組（桌面版與網頁版共用）
下載引擎: yt-dlp · 音訊轉換/影片合併: ffmpeg（自動探測）
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

VERSION = "2.0"

# ---------------------------------------------------------------- 路徑

def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


DEFAULT_OUT = app_dir() / "downloads"
HISTORY_FILE = app_dir() / "history.json"

# ---------------------------------------------------------------- 格式定義
# kind: audio / video；thumb: 嘗試嵌入封面與元資料

FORMAT_MAP = {
    # ---- 音訊 ----
    "mp3":      {"label": "MP3·推薦",    "kind": "audio",
                 "args": ["-x", "--audio-format", "mp3", "--audio-quality", "0"], "thumb": True},
    "m4a":      {"label": "M4A",         "kind": "audio",
                 "args": ["-x", "--audio-format", "m4a"], "thumb": True},
    "flac":     {"label": "FLAC·無損",   "kind": "audio",
                 "args": ["-x", "--audio-format", "flac"], "thumb": True},
    "wav":      {"label": "WAV·無損",    "kind": "audio",
                 "args": ["-x", "--audio-format", "wav"], "thumb": False},
    "abest":    {"label": "原始音質",     "kind": "audio",
                 "args": ["-f", "bestaudio/best"], "thumb": False},
    # ---- 視頻 ----
    "mp4-1080": {"label": "MP4·1080P",   "kind": "video",
                 "args": ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                          "--merge-output-format", "mp4"], "thumb": True},
    "mp4-720":  {"label": "MP4·720P",    "kind": "video",
                 "args": ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
                          "--merge-output-format", "mp4"], "thumb": True},
    "mp4-best": {"label": "MP4·最高畫質", "kind": "video",
                 "args": ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
                          "--merge-output-format", "mp4"], "thumb": True},
    "mkv-best": {"label": "MKV·原畫",     "kind": "video",
                 "args": ["-f", "bestvideo+bestaudio/best",
                          "--merge-output-format", "mkv"], "thumb": False},
}
AUDIO_IDS = [k for k, v in FORMAT_MAP.items() if v["kind"] == "audio"]
VIDEO_IDS = [k for k, v in FORMAT_MAP.items() if v["kind"] == "video"]
DEFAULT_FMT = {"audio": "mp3", "video": "mp4-1080"}

COOKIE_BROWSERS = [("不使用", ""), ("Edge", "edge"), ("Chrome", "chrome"),
                   ("Firefox", "firefox"), ("Brave", "brave")]

# ---------------------------------------------------------------- 狀態常量

S_QUEUED, S_DL, S_PROC = "排隊中", "下載中", "處理中"
S_DONE, S_FAIL, S_CANCEL = "完成", "失敗", "已取消"
STATUS_ACTIVE = (S_QUEUED, S_DL, S_PROC)
STATUS_DONE = (S_DONE, S_FAIL, S_CANCEL)

# ---------------------------------------------------------------- 引擎探測

def _local_appdata():
    return Path(os.environ.get("LOCALAPPDATA", ""))


def find_ytdlp():
    home = Path(os.path.expanduser("~"))
    cand = [shutil.which("yt-dlp")]
    for pat in (
        _local_appdata().glob("Packages/*/LocalCache/local-packages/Python*/Scripts/yt-dlp.exe"),
        home.glob("AppData/Roaming/Python/Python*/Scripts/yt-dlp.exe"),
        home.glob("AppData/Local/Programs/Python/Python*/Scripts/yt-dlp.exe"),
    ):
        cand.extend(sorted(pat))
    for c in cand:
        if c and Path(c).exists():
            return [str(c)]
    return [sys.executable, "-m", "yt_dlp"]


def find_ffmpeg():
    home = Path(os.path.expanduser("~"))
    cand = [shutil.which("ffmpeg")]
    for pat in (
        home.glob("AppData/Roaming/Python/Python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*.exe"),
        _local_appdata().glob("Packages/*/LocalCache/local-packages/Python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*.exe"),
        home.glob("AppData/Local/Programs/Python/Python*/site-packages/imageio_ffmpeg/binaries/ffmpeg-*.exe"),
    ):
        cand.extend(sorted(pat))
    for c in cand:
        if c and Path(c).exists():
            return str(c)
    return ""


YTDLP_CMD = find_ytdlp()
FFMPEG_PATH = find_ffmpeg()
SUBPROC_ENV = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_ytdlp_version = ""


def ytdlp_version():
    global _ytdlp_version
    if not _ytdlp_version:
        try:
            r = subprocess.run(YTDLP_CMD + ["--version"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=20, creationflags=CREATE_NO_WINDOW)
            _ytdlp_version = (r.stdout or "").strip() or "?"
        except Exception:
            _ytdlp_version = "?"
    return _ytdlp_version


# ---------------------------------------------------------------- 歷史記錄

_LOCK = threading.RLock()
HISTORY = []


def load_history():
    global HISTORY
    if HISTORY_FILE.exists():
        try:
            HISTORY = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            HISTORY = []


def save_history():
    try:
        HISTORY_FILE.write_text(json.dumps(HISTORY[:200], ensure_ascii=False, indent=1),
                                encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------- 任務管理

TASKS = {}          # id -> task dict
QUEUE = []          # 待處理 task id（FIFO）
WORKER_STARTED = False
UIQ = None          # GUI 模式下的執行緒 -> 主執行緒事件佇列


def _emit(task, **fields):
    with _LOCK:
        task.update(fields)
    if UIQ is not None:
        UIQ.put(("task", task["id"]))


def create_task(urls, fmt, outdir, cookie):
    task = {
        "id": uuid.uuid4().hex[:10],
        "urls": list(urls),
        "format": fmt,
        "outdir": outdir,
        "cookie": cookie,
        "status": S_QUEUED,
        "percent": 0.0, "speed": "", "eta": "", "item_note": "",
        "current_file": "", "files": [], "error": "", "has_warning": False,
        "cancel": False, "created": time.time(),
    }
    with _LOCK:
        TASKS[task["id"]] = task
        QUEUE.append(task["id"])
    _ensure_worker()
    return task["id"]


def _ensure_worker():
    global WORKER_STARTED
    if not WORKER_STARTED:
        WORKER_STARTED = True
        threading.Thread(target=_worker_loop, daemon=True).start()


def _worker_loop():
    while True:
        task = None
        with _LOCK:
            while QUEUE:
                tid = QUEUE.pop(0)
                t = TASKS.get(tid)
                if not t:
                    continue
                if t["cancel"]:
                    t["status"] = S_CANCEL
                    continue
                task = t
                break
        if task is None:
            time.sleep(0.25)
            continue
        try:
            _run_task(task, update=lambda **kw: _emit(task, **kw))
        except Exception as e:
            _emit(task, status=S_FAIL, error="內部錯誤: %s" % e)
        if UIQ is not None:
            UIQ.put(("history", None))


def _run_task(task, update=None):
    """執行單個下載任務（GUI、網頁、命令列共用）。"""
    def setf(**kw):
        if update:
            update(**kw)
        task.update(kw)

    fmt = FORMAT_MAP.get(task["format"], FORMAT_MAP["mp3"])
    outdir = Path(task["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    argv = list(YTDLP_CMD) + [
        "--newline", "--no-warnings", "--progress",
        "--progress-template",
        "download:PROG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "after_move:filepath",
        "--concurrent-fragments", "4",
        "-P", str(outdir),
        "-o", "%(title)s.%(ext)s",
    ]
    if FFMPEG_PATH:
        argv += ["--ffmpeg-location", FFMPEG_PATH]
    argv += list(fmt["args"])
    if fmt["thumb"] and FFMPEG_PATH:
        # 只嵌入元資料；封面嵌入需 ffprobe（imageio-ffmpeg 未附帶），故不用
        argv += ["--embed-metadata"]
    if task["cookie"]:
        argv += ["--cookies-from-browser", task["cookie"]]
    argv += list(task["urls"])

    setf(status=S_DL, current_file="", percent=0.0, speed="", eta="", error="")

    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                env=SUBPROC_ENV, cwd=str(outdir),
                                creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        setf(status=S_FAIL, error="無法啟動 yt-dlp: %s" % e)
        return

    with _LOCK:
        task["_proc"] = proc
    err_line = ""

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        with _LOCK:
            if task["cancel"]:
                break
        if line.startswith("PROG|"):
            parts = line.split("|")
            if len(parts) >= 2:
                m = re.search(r"[\d.]+", parts[1])
                setf(percent=float(m.group()) if m else 0.0,
                     speed=parts[2].strip() if len(parts) > 2 else "",
                     eta=parts[3].strip() if len(parts) > 3 else "")
        elif line.startswith("ERROR"):
            err_line = line
        elif line.startswith("["):
            if any(k in line for k in ("ExtractAudio", "Metadata", "EmbedThumbnail",
                                       "VideoConvertor", "Merger")):
                setf(status=S_PROC)
            else:
                m = re.search(r"Downloading item (\d+) of (\d+)", line)
                if m:
                    setf(item_note="第 %s/%s 個" % (m.group(1), m.group(2)), percent=0.0)
                m2 = re.match(r"\[download\] (.+?) has already been downloaded$", line)
                if m2:
                    p = Path(m2.group(1).strip())
                    if p.exists() and str(p) not in task["files"]:
                        setf(current_file=p.name)
                        task["files"].append(str(p))
        else:
            p = Path(line)
            if p.exists() and str(p) not in task["files"]:
                setf(current_file=p.name)
                task["files"].append(str(p))

    rc = proc.wait()
    with _LOCK:
        task.pop("_proc", None)

    if task["cancel"]:
        setf(status=S_CANCEL)
        return

    files = [f for f in task["files"] if Path(f).exists()]
    if files:
        task["files"] = files
        setf(percent=100.0, status=S_DONE, has_warning=rc != 0,
             error=err_line if rc != 0 else "")
        for f in files:
            with _LOCK:
                HISTORY.insert(0, {
                    "time": time.strftime("%Y-%m-%d %H:%M"),
                    "title": Path(f).stem,
                    "filepath": f,
                    "size": Path(f).stat().st_size,
                    "format": task["format"],
                    "kind": fmt["kind"],
                    "urls": task["urls"],
                })
            save_history()
    else:
        setf(status=S_FAIL, error=err_line or ("yt-dlp 退出碼 %d" % rc))


def cancel_task(tid):
    with _LOCK:
        task = TASKS.get(tid)
        if not task:
            return False
        task["cancel"] = True
        if task["status"] == S_QUEUED:
            task["status"] = S_CANCEL
        proc = task.get("_proc")
    if proc:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, timeout=10,
                               creationflags=CREATE_NO_WINDOW)
            else:
                proc.terminate()
        except Exception:
            pass
    if UIQ is not None:
        UIQ.put(("task", tid))
    return True


def fetch_info(url, cookie):
    argv = list(YTDLP_CMD) + ["--no-warnings", "--dump-single-json", "--flat-playlist"]
    if FFMPEG_PATH:
        argv += ["--ffmpeg-location", FFMPEG_PATH]
    if cookie:
        argv += ["--cookies-from-browser", cookie]
    argv.append(url)
    r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=SUBPROC_ENV, timeout=120,
                       creationflags=CREATE_NO_WINDOW)
    if r.returncode != 0:
        out = (r.stderr or r.stdout or "").strip()
        raise RuntimeError(out.splitlines()[-1] if out else "yt-dlp 失敗")
    data = json.loads(r.stdout)
    w, h = data.get("width"), data.get("height")
    return {
        "is_playlist": "entries" in data,
        "title": data.get("title") or "(未知標題)",
        "uploader": data.get("uploader") or data.get("channel") or "",
        "duration_string": data.get("duration_string") or "",
        "resolution": "%d×%d" % (w, h) if w and h else ("%dP" % h if h else ""),
        "n_entries": len(data.get("entries") or []) if "entries" in data else 1,
    }


def open_in_explorer(path):
    p = Path(path)
    if p.is_dir():
        os.startfile(str(p))  # noqa
    elif p.exists():
        subprocess.Popen('explorer /select,"%s"' % p, shell=True)
    else:
        raise RuntimeError("路徑不存在")


# ---------------------------------------------------------------- 自檢與命令列

def selftest():
    lines = []
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        lines.append("[%s] %s %s" % ("OK  " if cond else "FAIL", name, detail))
        if not cond:
            ok = False

    check("version", True, "MediaGrabber v%s（音訊+視頻，%d 種格式）"
          % (VERSION, len(FORMAT_MAP)))
    check("yt-dlp", bool(YTDLP_CMD), " ".join(YTDLP_CMD) + " (v%s)" % ytdlp_version())
    check("ffmpeg", bool(FFMPEG_PATH), FFMPEG_PATH)
    try:
        load_history()
        save_history()
        check("history.json", True, str(HISTORY_FILE))
    except Exception as e:
        check("history.json", False, str(e))
    check("tkinter", True, "Tk %.1f" % __import__("tkinter").TkVersion)

    log = app_dir() / "selftest.log"
    text = "MediaGrabber selftest %s\n" % ("PASSED" if ok else "FAILED") + "\n".join(lines)
    try:
        print(text)
    except Exception:
        pass
    log.write_text(text, encoding="utf-8")
    return 0 if ok else 1


def cli_download(url, fmt, outdir):
    if fmt not in FORMAT_MAP:
        print("不支援的格式: %s\n可選: %s" % (fmt, ", ".join(FORMAT_MAP)), file=sys.stderr)
        return 2
    load_history()
    task = {
        "id": "cli", "urls": [url], "format": fmt,
        "outdir": outdir or str(DEFAULT_OUT), "cookie": "",
        "status": S_DL, "percent": 0.0, "speed": "", "eta": "", "item_note": "",
        "current_file": "", "files": [], "error": "", "has_warning": False,
        "cancel": False, "created": time.time(),
    }

    def update(**kw):
        if "status" in kw:
            print("[%s] %s" % (kw["status"], task.get("current_file") or task["urls"][0]))
        elif "percent" in kw and kw["percent"]:
            print("  %5.1f%%  %s  剩餘 %s" % (kw["percent"], kw.get("speed", ""),
                                              kw.get("eta", "")),
                  end="\r" if kw["percent"] < 100 else "\n")

    _run_task(task, update=update)
    if task["status"] == S_DONE:
        print("完成:")
        for f in task["files"]:
            print("  " + f)
        return 0
    print("失敗: %s" % task["error"], file=sys.stderr)
    return 1
