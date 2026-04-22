# YouTube Downloader

一个本地运行、Web-first 的 YouTube 搜索、审核与下载工作台。

你可以用自然语言描述任务，系统会完成搜索、候选整理、人工审核和下载执行。它的重点不是“全自动代理”，而是一个可靠、可观察、适合日常使用的本地下载工作流。

## 一句话理解

- 普通用户：下载 release，双击启动，在浏览器里使用
- 开发者：拉源码、安装依赖、运行本地 Web 工作台

## 当前状态

- 默认产品形态：浏览器工作台
- 当前版本：`0.1.4`
- 目标平台：Windows
- 核心运行时：FastAPI + LangGraph + `yt-dlp`

## 这个项目能做什么

- 按主题搜索 YouTube 视频并生成候选列表
- 在下载前先人工审核候选视频
- 批量下载视频或音频
- 在本地保留任务记录、审核结果、下载会话和运行状态

## 普通用户如何开始

推荐直接使用 Windows Release，而不是从源码启动。

### 下载哪一个

- 安装版：`youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`
- 便携版：`youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`

### 里面已经包含什么

- Python runtime
- Web 应用
- `yt-dlp`
- `ffmpeg` / `ffprobe`

### 如何启动

双击 `youtube-downloader.exe` 后，程序会启动本地服务并自动打开浏览器。

更多发布说明见：

- [docs/WINDOWS_RELEASE.md](docs/WINDOWS_RELEASE.md)

## 开发者如何开始

如果你是在仓库里本地开发，而不是使用 release：

### 环境要求

推荐统一使用 Miniconda `base` 环境，并确保至少具备：

- `langgraph`
- `fastapi`
- `uvicorn`
- `yt-dlp`

### 安装依赖

```powershell
conda run -n base python -m pip install -U -r requirements-dev.txt
```

### 启动本地工作台

```powershell
.\run_web.bat
```

默认地址：

```text
http://127.0.0.1:8000
```

### 只做环境自检

```powershell
.\run_web.bat -CheckOnly
```

### 手动启动

```powershell
conda run -n base python -m uvicorn --app-dir . app.web.main:app --host 127.0.0.1 --port 8000 --reload
```

## 仓库结构

```text
app/
  agent/       planner / runtime / task state
  core/        搜索、筛选、下载、结果与路径服务
  tools/       agent tool wrappers
  web/         FastAPI、静态前端、release 启动入口
docs/
tests/
scripts/
packaging/
```

## 主要入口

- `app/web/main.py`
  - 本地 Web API 与静态前端入口
- `app/web/static/`
  - 浏览器工作台
- `youtube_batch.py`
  - 兼容 CLI 入口
- `gui_app.py`
  - legacy 桌面兼容壳，不再作为默认产品入口

## 依赖分层

- `requirements.txt`
  - 运行时基线，Web / Agent / CLI / release runtime 共用
- `requirements-dev.txt`
  - 本地开发与测试安装入口
- `requirements-release.txt`
  - 打包额外依赖，例如 `pyinstaller`

## 本地构建 Windows Release

```powershell
conda run -n base python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1
```

构建产物位于：

```text
build/release/
```

## 测试基线

优先保护 Web 工作台主链路与核心 API 契约：

```powershell
conda run -n base python -m unittest discover -s tests -p "test_app_paths.py"
conda run -n base python -m unittest discover -s tests -p "test_web_workspace_smoke.py"
```

如果改动涉及状态流、审核、结果、LangGraph runtime 或 release 路径，再补跑对应后端契约测试。

## 版本与发布

当前版本基线由仓库根目录的 `VERSION` 文件维护。

发布一个新版本时，按这个顺序收口：

1. 更新 `VERSION`
2. 更新 `CHANGELOG.md`
3. 运行 release 构建与 smoke
4. 提交并打 `vX.Y.Z` tag
5. 推送 tag，触发 GitHub Release 工作流

## 项目边界

这个项目当前重点是一个可靠的本地 Web agent，而不是完全自治的多 agent 系统。

默认强调：

- 本地运行
- 可观察的任务状态
- 下载前人工确认
- 复用已有后端能力，而不是驱动 GUI 自动化

## 免责声明

本项目仅用于合法、合规的内容获取与研究用途。

请遵守 YouTube 服务条款及所在司法辖区法律法规，不得用于侵权或非法用途。

## License

MIT
