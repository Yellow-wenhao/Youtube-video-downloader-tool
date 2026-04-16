# YouTube Downloader

一个 Web-first、本地运行的 YouTube 搜索、审核与下载工具。  
当前默认产品形态是浏览器工作台，不再以旧 PySide GUI 作为主入口。

## 面向普通用户的使用方式

推荐直接下载 Windows Release：

- 安装版：`youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`
- 便携版：`youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`

Release 已内置：

- Python runtime
- Web 应用
- `yt-dlp`
- `ffmpeg` / `ffprobe`

双击 `youtube-downloader.exe` 后，会静默启动本地服务并自动打开浏览器。

更多说明见：

- [docs/WINDOWS_RELEASE.md](docs/WINDOWS_RELEASE.md)

## 当前产品方向

- Web 工作台是默认本地入口
- `app/web/main.py`
  - 本地 Web API 与静态前端入口
- `app/web/static/`
  - 浏览器工作台
- `gui_app.py`
  - legacy 兼容入口，只保留迁移参考与必要修复
- `youtube_batch.py`
  - 兼容 CLI 入口

## 仓库结构

```text
app/
  agent/       planner / runner / prompts
  core/        搜索、筛选、下载、路径与结果服务
  tools/       agent tool wrappers
  web/         FastAPI + 静态前端 + release 启动入口
docs/
tests/
scripts/
```

## 开发环境运行

如果你是在源码仓库里开发，而不是使用 release：

```powershell
conda run -n <your-conda-env> python -m pip install -U -r requirements.txt
.\run_web.bat
```

或手动启动：

```powershell
conda run -n <your-conda-env> python -m uvicorn --app-dir . app.web.main:app --host 127.0.0.1 --port 8000 --reload
```

默认浏览器地址：

```text
http://127.0.0.1:8000
```

`run_web.ps1` / `run_web.bat` 现在是开发态脚本，不是最终发布物。

## 本地构建 Windows Release

```powershell
python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1 -Version 0.1.0
```

构建产物位于：

```text
build/release/
```

GitHub tag `vX.Y.Z` 会触发自动构建并上传 release 资产。

## 测试基线

优先保护 Web 工作台主链路与核心 API 合约：

```powershell
conda run -n <your-conda-env> python -m unittest discover -s tests -p "test_app_paths.py"
conda run -n <your-conda-env> python -m unittest discover -s tests -p "test_web_workspace_smoke.py"
```

如涉及状态流、审核、结果、planner 或 release 路径逻辑，再补对应后端契约测试。

## 免责声明

本项目仅用于合法、合规的内容获取与研究用途。  
请遵守 YouTube 服务条款及所在司法辖区法律法规，不得用于侵权或非法用途。

## License

MIT
