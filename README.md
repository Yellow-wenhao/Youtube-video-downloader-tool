# YouTube Downloader

一个 Web-first、本地运行的 YouTube 搜索、审核与下载工具。  

## 面向普通用户的使用方式

推荐直接使用 Windows Release：

- 安装版：`youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`
- 便携版：`youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`

Release 内置：

- Python runtime
- Web 应用
- `yt-dlp`
- `ffmpeg` / `ffprobe`

双击 `youtube-downloader.exe` 后，会自动启动本地服务并打开浏览器。

更多说明见：

- [docs/WINDOWS_RELEASE.md](docs/WINDOWS_RELEASE.md)

## 当前产品方向

- Web 工作台是默认本地入口
- `app/web/main.py`
  - 本地 Web API 与静态前端入口
- `app/web/static/`
  - 浏览器工作台
- `gui_app.py`
  - legacy 桌面兼容壳，不再作为默认产品入口
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

当前标准开发解释器是 Miniconda `base` 环境，要求至少具备：

- `langgraph`
- `fastapi`
- `uvicorn`
- `yt-dlp`

推荐直接使用仓库内启动脚本：

```powershell
conda run -n base python -m pip install -U -r requirements-dev.txt
.\run_web.bat
```

如只想先做环境自检，不启动服务：

```powershell
.\run_web.bat -CheckOnly
```

如需覆盖默认环境名，可设置：

```powershell
$env:YTBDLP_CONDA_ENV="your-env-name"
.\run_web.bat
```

手动启动方式：

```powershell
conda run -n base python -m uvicorn --app-dir . app.web.main:app --host 127.0.0.1 --port 8000 --reload
```

默认浏览器地址：

```text
http://127.0.0.1:8000
```

`run_web.ps1` / `run_web.bat` 现在是开发态脚本，不是最终发布物。它们默认假设你使用统一的 conda 解释器，而不是任意本机 Python。

## 本地构建 Windows Release

```powershell
conda run -n base python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1
```

依赖分层约定：

- `requirements.txt`
  - 运行时基线，Web / Agent / CLI / release runtime 都依赖这里，`langgraph` 必须放在这里
- `requirements-dev.txt`
  - 本地开发与测试入口，在运行时基线上补充开发依赖
- `requirements-release.txt`
  - 仅放打包额外依赖，例如 `pyinstaller`，不要把 `langgraph`、`fastapi`、`uvicorn` 之类运行时包移到这里

构建产物位于：

```text
build/release/
```

## 版本与发布流程

当前版本基线由仓库根目录的 `VERSION` 文件维护。

发布一个新版本时，按这个顺序收口：

1. 更新 `VERSION`
2. 更新 `CHANGELOG.md`
3. 运行 release 构建与 smoke
4. 提交并打 `vX.Y.Z` tag
5. 推送 tag，触发 GitHub Release 工作流

GitHub tag `vX.Y.Z` 会触发自动构建并上传 release 资产。工作流会校验 tag 版本与 `VERSION` 一致。

## 测试基线

优先保护 Web 工作台主链路与核心 API 契约：

```powershell
conda run -n base python -m unittest discover -s tests -p "test_app_paths.py"
conda run -n base python -m unittest discover -s tests -p "test_web_workspace_smoke.py"
```

如涉及状态流、审核、结果、planner、LangGraph runtime 或 release 路径逻辑，再补对应后端契约测试。

## 免责声明

本项目仅用于合法、合规的内容获取与研究用途。

请遵守 YouTube 服务条款及所在司法辖区法律法规，不得用于侵权或非法用途。

## License

MIT
