# -*- coding: utf-8 -*-
"""
MediaGrabber 2.0 桌面版 —— 影音爬取工具（tkinter 原生視窗，無需瀏覽器）
下載引擎: yt-dlp · 音訊轉換/影片合併: ffmpeg（自動探測）

用法:
    MediaGrabber.exe                              開啟圖形介面
    python media_grabber_gui.py --selftest        環境自檢（寫 selftest.log）
    python media_grabber_gui.py --download URL [--format mp3] [--outdir DIR]
                                                  命令列直接下載
"""
import os
import queue as queue_mod
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import grabber_core as core
from grabber_core import (
    VERSION, FORMAT_MAP, AUDIO_IDS, VIDEO_IDS, DEFAULT_FMT, COOKIE_BROWSERS,
    STATUS_ACTIVE, STATUS_DONE, S_QUEUED, S_DL, S_PROC, S_DONE, S_FAIL, S_CANCEL,
    TASKS, HISTORY,
    DEFAULT_OUT, FFMPEG_PATH,
    load_history, save_history, create_task, cancel_task, fetch_info,
    ytdlp_version, open_in_explorer, app_dir,
)

# ---------------------------------------------------------------- 主題色
BG      = "#0d0f14"
CARD    = "#161a23"
CARD2   = "#1c2130"
LINE    = "#262c3d"
TEXT    = "#e8ecf4"
DIM     = "#8b93a7"
ACCENT  = "#7c5cff"
ACCENT2 = "#2dd4bf"
DANGER  = "#ff5c7a"
OK      = "#34d399"
WARN    = "#fbbf24"
CHIP_BG = {S_QUEUED: "#2a3040", S_DL: "#1e3a5f", S_PROC: "#3f3418",
           S_DONE: "#143528", S_FAIL: "#3f1c26", S_CANCEL: "#2a3040"}
CHIP_FG = {S_QUEUED: DIM, S_DL: "#7db4ff", S_PROC: WARN,
           S_DONE: OK, S_FAIL: DANGER, S_CANCEL: DIM}


def run_gui():
    core.UIQ = queue_mod.Queue()
    UIQ = core.UIQ

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.title("MediaGrabber %s · 影音爬取工具" % VERSION)
    # DPI 感知下字型由 tk 自動縮放，但視窗幾何不會，需按真實 DPI 同步放大
    S = max(1.0, root.winfo_fpixels("1i") / 96.0)   # 150% 縮放屏 → 1.5
    root.geometry("%dx%d" % (int(900 * S), int(820 * S)))
    root.minsize(int(820 * S), int(700 * S))
    root.configure(bg=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Accent.Horizontal.TProgressbar", troughcolor="#10131a",
                    background=ACCENT, lightcolor=ACCENT, darkcolor="#6366f1",
                    bordercolor=CARD, thickness=8)
    style.configure("TScrollbar", troughcolor=BG, background=CARD2, bordercolor=BG)

    F = lambda size=10, bold=False: ("Microsoft YaHei UI", size, "bold" if bold else "normal")

    load_history()

    # ---------- 頂部
    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=18, pady=(14, 4))
    tk.Label(head, text="MediaGrabber", font=F(16, True), fg=ACCENT2, bg=BG).pack(side="left")
    tk.Label(head, text="  影音爬取工具 v%s（桌面版）" % VERSION, font=F(10), fg=DIM,
             bg=BG).pack(side="left")
    env_text = "yt-dlp %s · ffmpeg %s" % (ytdlp_version(), "✓" if FFMPEG_PATH else "✗ 未找到")
    tk.Label(head, text=env_text, font=F(9), fg=OK if FFMPEG_PATH else DANGER,
             bg=BG).pack(side="right")

    # ---------- 連結卡片
    card1 = tk.Frame(root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    card1.pack(fill="x", padx=18, pady=6)
    tk.Label(card1, text="影片連結（每行一個，支持 B 站 / YouTube / 抖音等）",
             font=F(9), fg=DIM, bg=CARD, anchor="w").pack(fill="x", padx=14, pady=(10, 4))
    txt = tk.Text(card1, height=4, bg=CARD2, fg=TEXT, insertbackground=TEXT,
                  relief="flat", font=F(10), padx=10, pady=8, wrap="char")
    txt.pack(fill="x", padx=14)
    txt.insert("1.0", "https://www.bilibili.com/video/BV1TL4y1h7AV/")

    type_var = tk.StringVar(value="audio")
    fmt_var = tk.StringVar(value=DEFAULT_FMT["audio"])

    row1 = tk.Frame(card1, bg=CARD)
    row1.pack(fill="x", padx=14, pady=(10, 4))
    tk.Label(row1, text="下載類型", font=F(9), fg=DIM, bg=CARD).pack(side="left", padx=(0, 8))
    tk.Radiobutton(row1, text="🎵 音頻", variable=type_var, value="audio",
                   command=lambda: on_type(), bg=CARD, fg=TEXT, selectcolor=CARD2,
                   activebackground=CARD, activeforeground=TEXT,
                   highlightthickness=0, font=F(9)).pack(side="left", padx=(0, 4))
    tk.Radiobutton(row1, text="🎬 視頻", variable=type_var, value="video",
                   command=lambda: on_type(), bg=CARD, fg=TEXT, selectcolor=CARD2,
                   activebackground=CARD, activeforeground=TEXT,
                   highlightthickness=0, font=F(9)).pack(side="left", padx=(0, 14))
    tk.Label(row1, text="Cookie（會員內容選瀏覽器）", font=F(9), fg=DIM,
             bg=CARD).pack(side="left", padx=(0, 6))
    cookie_box = ttk.Combobox(row1, state="readonly", width=8,
                              values=[c[0] for c in COOKIE_BROWSERS])
    cookie_box.current(0)
    cookie_box.pack(side="left")

    row_a = tk.Frame(card1, bg=CARD)
    row_v = tk.Frame(card1, bg=CARD)

    def build_radios(parent, ids):
        for fid in ids:
            tk.Radiobutton(parent, text=FORMAT_MAP[fid]["label"], variable=fmt_var,
                           value=fid, command=update_hint, bg=CARD, fg=TEXT,
                           selectcolor=CARD2, activebackground=CARD,
                           activeforeground=TEXT, highlightthickness=0,
                           font=F(9)).pack(side="left", padx=(0, 4))
    build_radios(row_a, AUDIO_IDS)
    build_radios(row_v, VIDEO_IDS)

    def on_type():
        if type_var.get() == "audio":
            row_v.pack_forget()
            row_a.pack(fill="x", padx=14, pady=(2, 4), after=row1)
            fmt_var.set(DEFAULT_FMT["audio"])
        else:
            row_a.pack_forget()
            row_v.pack(fill="x", padx=14, pady=(2, 4), after=row1)
            fmt_var.set(DEFAULT_FMT["video"])
        update_hint()
    row_a.pack(fill="x", padx=14, pady=(2, 4), after=row1)

    fmt_hint = tk.Label(card1, text="", font=F(9), fg=WARN, bg=CARD, anchor="w")

    def update_hint(*_):
        if FFMPEG_PATH:
            fmt_hint.pack_forget()
            return
        if type_var.get() == "video":
            fmt_hint.config(text="⚠ 未偵測到 ffmpeg，影片功能不可用", fg=WARN)
            fmt_hint.pack(fill="x", padx=14, pady=(0, 2))
        elif fmt_var.get() == "abest":
            fmt_hint.pack_forget()
        else:
            fmt_hint.config(text="⚠ 未偵測到 ffmpeg，僅音頻「原始音質」可用", fg=WARN)
            fmt_hint.pack(fill="x", padx=14, pady=(0, 2))
    update_hint()

    row3 = tk.Frame(card1, bg=CARD)
    row3.pack(fill="x", padx=14, pady=(6, 12))
    tk.Label(row3, text="保存目錄", font=F(9), fg=DIM, bg=CARD).pack(side="left", padx=(0, 8))
    outdir_var = tk.StringVar(value=str(DEFAULT_OUT))
    tk.Entry(row3, textvariable=outdir_var, bg=CARD2, fg=TEXT,
             insertbackground=TEXT, relief="flat", font=F(9)).pack(
        side="left", fill="x", expand=True, ipady=6)

    def browse():
        d = filedialog.askdirectory(initialdir=outdir_var.get() or str(app_dir()))
        if d:
            outdir_var.set(os.path.normpath(d))
    tk.Button(row3, text="瀏覽…", font=F(9), bg=CARD2, fg=TEXT, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=12,
              command=browse).pack(side="left", padx=(8, 0))

    def open_outdir():
        d = outdir_var.get().strip() or str(DEFAULT_OUT)
        try:
            open_in_explorer(d)
        except Exception as e:
            messagebox.showerror("錯誤", str(e))
    tk.Button(row3, text="📂 打開目錄", font=F(9), bg=CARD2, fg=TEXT, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=12,
              command=open_outdir).pack(side="left", padx=(8, 0))

    info_label = tk.Label(card1, text="", font=F(10), fg=ACCENT2, bg=CARD,
                          wraplength=int(820 * S), justify="left", anchor="w")
    info_label.pack(fill="x", padx=14, pady=(0, 10))

    def get_urls():
        return [s.strip() for s in txt.get("1.0", "end").split("\n") if s.strip()]

    def cookie_val():
        return dict(COOKIE_BROWSERS)[cookie_box.get()]

    def do_info():
        urls = get_urls()
        if not urls:
            messagebox.showwarning("提示", "請先貼上影片連結")
            return
        info_label.config(text="正在取得資訊…", fg=DIM)

        def work():
            try:
                info = fetch_info(urls[0], cookie_val())
                bits = [info["title"]]
                if info["uploader"]:
                    bits.append("UP主: " + info["uploader"])
                if info["duration_string"]:
                    bits.append("時長: " + info["duration_string"])
                if info["resolution"]:
                    bits.append("解析度: " + info["resolution"])
                if info["is_playlist"]:
                    bits.append("🎵 播放清單，共 %d 個影片" % info["n_entries"])
                UIQ.put(("info", " · ".join(bits), ACCENT2))
            except Exception as e:
                UIQ.put(("info", "取得失敗: %s" % e, DANGER))
        threading.Thread(target=work, daemon=True).start()

    def do_download():
        urls = get_urls()
        if not urls:
            messagebox.showwarning("提示", "請先貼上影片連結")
            return
        fmt = FORMAT_MAP[fmt_var.get()]
        if not FFMPEG_PATH and (fmt["kind"] == "video" or fmt["args"]):
            messagebox.showwarning(
                "提示", "未偵測到 ffmpeg，%s" %
                ("影片功能不可用" if fmt["kind"] == "video" else "僅音頻「原始音質」可用"))
            return
        outdir = os.path.expanduser(outdir_var.get().strip())
        if not outdir:
            outdir = str(DEFAULT_OUT)
        create_task(urls, fmt_var.get(), os.path.normpath(outdir), cookie_val())

    btns = tk.Frame(card1, bg=CARD)
    btns.pack(fill="x", padx=14, pady=(8, 12))
    tk.Button(btns, text="獲取資訊", font=F(10), bg=CARD2, fg=TEXT, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=22, pady=6,
              command=do_info).pack(side="right")
    tk.Button(btns, text="開始下載", font=F(10, True), bg=ACCENT, fg="#ffffff",
              relief="flat", activebackground="#6366f1", activeforeground="#ffffff",
              padx=22, pady=6, command=do_download).pack(side="right", padx=(0, 10))

    # ---------- 隊列卡片
    card2 = tk.Frame(root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    qhead = tk.Frame(card2, bg=CARD)
    qhead.pack(fill="x", padx=14, pady=(10, 4))
    tk.Label(qhead, text="下載隊列", font=F(11, True), fg=TEXT, bg=CARD).pack(side="left")

    def clear_done():
        with core._LOCK:
            for tid in [t["id"] for t in TASKS.values() if t["status"] in STATUS_DONE]:
                TASKS.pop(tid, None)
    tk.Button(qhead, text="清空已完成", font=F(9), bg=CARD2, fg=DIM, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=10,
              command=clear_done).pack(side="right")

    qwrap = tk.Frame(card2, bg=CARD)
    qwrap.pack(fill="both", expand=True, padx=8, pady=(2, 10))
    canvas = tk.Canvas(qwrap, bg=CARD, highlightthickness=0)
    qsb = ttk.Scrollbar(qwrap, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=qsb.set)
    qsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    inner = tk.Frame(canvas, bg=CARD)
    inner_win = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner_win, width=e.width))
    root.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

    # ---------- 歷史（先 pack，讓隊列卡只吃剩餘空間）
    card3 = tk.Frame(root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
    card3.pack(fill="x", padx=18, pady=(6, 14), before=card2)
    hhead = tk.Frame(card3, bg=CARD)
    hhead.pack(fill="x", padx=14, pady=(10, 4))
    tk.Label(hhead, text="下載記錄（history.json）", font=F(11, True), fg=TEXT,
             bg=CARD).pack(side="left")

    def clear_history():
        with core._LOCK:
            HISTORY.clear()
        save_history()
        refresh_history()
    tk.Button(hhead, text="清空", font=F(9), bg=CARD2, fg=DIM, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=10,
              command=clear_history).pack(side="right")

    hlist = tk.Listbox(card3, bg=CARD2, fg=TEXT, relief="flat", height=5,
                       font=F(9), selectbackground="#2a3040", selectforeground=TEXT,
                       activestyle="none")
    hlist.pack(fill="x", padx=14, pady=(0, 4))
    _hist_paths = []

    def refresh_history():
        nonlocal _hist_paths
        hlist.delete(0, "end")
        _hist_paths = []
        with core._LOCK:
            items = list(HISTORY)
        for h in items[:60]:
            size = h.get("size", 0)
            size_s = "%.1f MB" % (size / 1048576) if size >= 1048576 else "%.0f KB" % (size / 1024)
            icon = "🎬" if h.get("kind") == "video" else "🎧"
            hlist.insert("end", "%s  %s %s  (%s)" % (h.get("time", ""), icon,
                                                     h.get("title", ""), size_s))
            _hist_paths.append(h.get("filepath", ""))

    def open_selected():
        sel = hlist.curselection()
        if not sel:
            return
        p = _hist_paths[sel[0]]
        if p:
            try:
                open_in_explorer(p)
            except Exception as e:
                messagebox.showerror("錯誤", str(e))
    tk.Button(card3, text="📂 打開所選位置", font=F(9), bg=CARD2, fg=TEXT, relief="flat",
              activebackground=CARD2, activeforeground=TEXT, padx=10,
              command=open_selected).pack(anchor="e", padx=14, pady=(0, 10))

    # ---------- 任務卡片渲染
    cards = {}   # tid -> widget refs

    def make_card(parent, task):
        f = tk.Frame(parent, bg=CARD2, highlightbackground=LINE, highlightthickness=1)
        f.pack(fill="x", pady=4, padx=2)
        top = tk.Frame(f, bg=CARD2)
        top.pack(fill="x", padx=12, pady=(8, 0))
        name = tk.Label(top, text="", font=F(10, True), fg=TEXT, bg=CARD2, anchor="w")
        name.pack(side="left", fill="x", expand=True)
        chip = tk.Label(top, text="", font=F(9, True), bg=CHIP_BG[S_QUEUED],
                        fg=CHIP_FG[S_QUEUED], padx=10, pady=2)
        chip.pack(side="right")
        cancel = tk.Button(top, text="取消", font=F(8), bg="#2a3040", fg=TEXT,
                           relief="flat", activebackground="#3a4152",
                           activeforeground=TEXT, padx=8,
                           command=lambda: cancel_task(task["id"]))
        cancel.pack(side="right", padx=(0, 8))
        bar = ttk.Progressbar(f, style="Accent.Horizontal.TProgressbar", maximum=100)
        bar.pack(fill="x", padx=12, pady=8)
        meta = tk.Label(f, text="", font=F(8), fg=DIM, bg=CARD2, anchor="w")
        meta.pack(fill="x", padx=12)
        err = tk.Label(f, text="", font=F(8), fg=DANGER, bg=CARD2,
                       wraplength=int(800 * S), justify="left", anchor="w")
        err.pack(fill="x", padx=12)
        files_frame = tk.Frame(f, bg=CARD2)
        files_frame.pack(fill="x", padx=12, pady=(0, 8))
        return {"frame": f, "name": name, "chip": chip, "cancel": cancel,
                "bar": bar, "meta": meta, "err": err,
                "files_frame": files_frame, "nfiles": 0, "status": ""}

    def sync_cards():
        with core._LOCK:
            tasks = sorted(TASKS.values(), key=lambda t: t["created"], reverse=True)
            snapshot = [{k: v for k, v in t.items() if k != "_proc"} for t in tasks]
        ids = [t["id"] for t in snapshot]
        for tid in list(cards):
            if tid not in ids:
                cards[tid]["frame"].destroy()
                del cards[tid]
        for t in snapshot:
            c = cards.get(t["id"])
            if c is None:
                c = make_card(inner, t)
                cards[t["id"]] = c
            c["frame"].lift()
            if c["status"] != t["status"]:
                c["status"] = t["status"]
                c["chip"].config(text=t["status"], bg=CHIP_BG.get(t["status"], CARD),
                                 fg=CHIP_FG.get(t["status"], TEXT))
                c["cancel"].pack_forget()
                if t["status"] in STATUS_ACTIVE:
                    c["cancel"].pack(side="right", padx=(0, 8))
                c["bar"].configure(value=100 if t["status"] == S_DONE else 0)
            c["name"].config(text=(t["current_file"] or t["urls"][0]))
            if t["status"] in STATUS_ACTIVE:
                c["bar"].configure(value=t["percent"])
            c["meta"].config(text="  ".join(x for x in [
                t["item_note"],
                ("%d%%" % t["percent"]) if t["percent"] else "",
                t["speed"], ("剩餘 " + t["eta"]) if t["eta"] and t["status"] == S_DL else "",
            ] if x))
            if t["error"]:
                c["err"].config(text=t["error"])
            while c["nfiles"] < len(t["files"]):
                fp = t["files"][c["nfiles"]]
                c["nfiles"] += 1
                row = tk.Frame(c["files_frame"], bg="#10131a")
                row.pack(fill="x", pady=2)
                icon = "🎬" if FORMAT_MAP.get(t["format"], {}).get("kind") == "video" else "🎧"
                tk.Label(row, text="%s %s" % (icon, Path(fp).name), font=F(8), fg=TEXT,
                         bg="#10131a", anchor="w").pack(side="left", fill="x",
                                                        expand=True, padx=8, pady=3)
                tk.Button(row, text="📂 打開位置", font=F(8), bg=CARD2, fg=TEXT,
                          relief="flat", activebackground=CARD2, activeforeground=TEXT,
                          padx=8, command=lambda p=fp: open_in_explorer(p)
                          ).pack(side="right", padx=6, pady=2)

    def tick():
        """主執行緒循環：消費 worker 事件並刷新任務卡片。"""
        try:
            while True:
                evt = UIQ.get_nowait()
                if evt[0] == "info":
                    info_label.config(text=evt[1], fg=evt[2])
                elif evt[0] == "history":
                    refresh_history()
        except queue_mod.Empty:
            pass
        sync_cards()
        root.after(200, tick)

    refresh_history()
    tick()

    def on_close():
        with core._LOCK:
            procs = [t.get("_proc") for t in TASKS.values() if t.get("_proc")]
        for p in procs:
            try:
                core.subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                                    capture_output=True, timeout=5,
                                    creationflags=core.CREATE_NO_WINDOW)
            except Exception:
                pass
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


# ---------------------------------------------------------------- 入口

def main():
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(core.selftest())
    if "--download" in argv:
        i = argv.index("--download")
        url = argv[i + 1] if len(argv) > i + 1 else ""
        fmt = "mp3"
        outdir = ""
        if "--format" in argv:
            fmt = argv[argv.index("--format") + 1]
        if "--outdir" in argv:
            outdir = argv[argv.index("--outdir") + 1]
        if not url:
            print("用法: --download URL [--format %s] [--outdir DIR]"
                  % "|".join(FORMAT_MAP), file=sys.stderr)
            sys.exit(2)
        sys.exit(core.cli_download(url, fmt, outdir))
    run_gui()


if __name__ == "__main__":
    main()
