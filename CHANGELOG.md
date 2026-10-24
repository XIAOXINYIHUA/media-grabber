# Changelog

本项目所有重要变更记录在此。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循[语义化版本](https://semver.org/lang/zh-CN/)。

## [2.0.0] - 2026-10-24

### Added
- 視頻下載：MP4 1080P / 720P / 最高畫質、MKV 原畫，ffmpeg 自動合流音畫軌。
- 下載類型切換（🎵 音頻 / 🎬 視頻），格式選項聯動。
- 資訊預覽新增解析度顯示；歷史記錄帶音頻/視頻標記。
- 分段下載並行加速（concurrent-fragments）。
- 桌面版新增「打開目錄」按鈕。

### Changed
- 抽出共用核心 `grabber_core.py`，桌面版 / 網頁版 / 命令列三入口共用同一套任務隊列與下載邏輯。
- 界面文案全面改為繁體中文；高 DPI 視窗幾何自適應。

## [1.0.0] - 2026-10-05

### Added
- 首個版本：網頁版 + 桌面版 exe，音頻下載（MP3 / M4A / FLAC / WAV / 原始音質）、批量隊列、歷史記錄、瀏覽器 Cookie 支持。

[2.0.0]: https://github.com/XIAOXINYIHUA/media-grabber/releases/tag/v2.0.0
[1.0.0]: https://github.com/XIAOXINYIHUA/media-grabber/releases/tag/v1.0.0
