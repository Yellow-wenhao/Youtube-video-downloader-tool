# Windows Release 使用说明

## 发布物

- 安装版：`youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`
- 便携版：`youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`

两者都内置：

- Python runtime
- Web 工作台
- `yt-dlp`
- `ffmpeg`
- `ffprobe`

普通用户不需要先安装 Python、conda、`yt-dlp` 或 `ffmpeg`。

## 启动方式

- 安装版：安装后从开始菜单或桌面快捷方式启动
- 便携版：解压后双击 `youtube-downloader.exe`

启动后会：

1. 静默启动本地后台服务
2. 自动打开默认浏览器
3. 进入本地工作台页面

如果浏览器没有自动打开，启动器会提示本地访问地址。

## 默认目录

- 下载目录：`Downloads\YouTube Downloader`
- 应用数据：`AppData\Local\YouTube Downloader`
- 日志与运行时状态：`AppData\Local\YouTube Downloader\logs` 和 `runtime`

## 已知限制

- 当前只提供 Windows x64 发布物
- 首版未做代码签名，Windows Defender / SmartScreen 可能提示“未知发布者”
- 本地后台服务在无页面/API 活动且无后台任务持续 15 分钟后会自动退出

## 开发者构建

本地手动构建：

```powershell
python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1 -Version 0.1.0
```

GitHub 发布：

- 推送 `vX.Y.Z` tag 后，GitHub Actions 会自动构建
- Release 资产会自动附加到对应 GitHub Release
