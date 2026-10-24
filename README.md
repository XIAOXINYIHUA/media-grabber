# MediaGrabber

基於 yt-dlp + ffmpeg 的本地下載器：貼上連結即可下載 B 站、YouTube、抖音等上千個站點的**音頻與視頻**，提供桌面視窗（tkinter）與本機網頁兩種界面。

![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)

## 快速開始

安裝依賴（Python 3.8+，本專案在 3.13 開發測試）：

```console
$ pip install yt-dlp imageio-ffmpeg
```

啟動桌面版（推薦）：

```console
$ python media_grabber_gui.py
```

或啟動網頁版（自動打開 http://127.0.0.1:8765）：

```console
$ python server.py
```

Windows 用戶可到本倉庫的 Releases 頁面下載 `MediaGrabber.exe`，雙擊即用（仍需本機已安裝上述依賴）。環境自檢：`python media_grabber_gui.py --selftest`。

## 功能一覽

- **音頻下載**：MP3（320K）/ M4A / FLAC / WAV / 原始音質，自動嵌入元資料
- **視頻下載**：MP4 1080P / 720P / 最高畫質、MKV 原畫，ffmpeg 自動合流音畫軌
- **批量隊列**：多行連結 + 播放清單整頁下載，實時進度、速度、剩餘時間，隨時取消
- **下載記錄**：history.json 持久化，帶音頻/視頻標記，一鍵打開文件位置
- **會員內容**：選擇瀏覽器 Cookie（Edge / Chrome / Firefox / Brave）可下載登錄/大會員內容
- **資訊預覽**：獲取標題、UP 主、時長、解析度（網頁版另帶封面圖）

## 輸出格式

| 類型 | 格式 | 說明 |
|---|---|---|
| 🎵 音頻 | MP3 · M4A · FLAC · WAV | 轉碼輸出，FLAC/WAV 無損 |
| | 原始音質 | 不轉碼，直接保存站點音軌 |
| 🎬 視頻 | MP4 1080P / 720P | 畫質上限控制 |
| | MP4 最高畫質 | 不限解析度，優先 mp4/m4a 流 |
| | MKV 原畫 | 任意站點流直封 MKV，兼容性最好 |

## 架構

三個入口共用同一套核心邏輯（`grabber_core.py`）：任務隊列、進度解析、歷史記錄與引擎探測。

```text
media_grabber_gui.py ─┐
server.py ────────────┼─→ grabber_core.py ─→ yt-dlp（下載）+ ffmpeg（轉碼/合流）
CLI --download ───────┘
```

## 命令列用法

```console
$ python media_grabber_gui.py --download URL --format mp4-720 [--outdir DIR]
```

格式 ID 見上表：`mp3 / m4a / flac / wav / abest / mp4-1080 / mp4-720 / mp4-best / mkv-best`。

## 限制

- 僅支援 Windows（視窗 DPI 適配、打開文件位置等使用了 Windows API）
- B 站 1080P 以上、YouTube 高清需要會員 Cookie；站點解析失效時通常更新 yt-dlp 即可（`pip install -U yt-dlp`）
- 視頻封面嵌入需要 ffprobe（pip 版 imageio-ffmpeg 未附帶），故僅嵌入元資料
- 下載的內容版權歸權利人所有，本工具僅供個人學習與備份，請遵守當地法律與目標網站條款

## 致謝與依賴

本工具的下載能力基於以下開源項目構建（運行時自動探測調用，不隨本工具分發）：

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（Unlicense / 公有領域）— 站點解析與下載引擎
- [ffmpeg](https://ffmpeg.org)（LGPL/GPL）— 音頻轉碼與視頻合流

感謝上述項目的維護者。

## License

待定（見 LICENSE 文件）。
