# Windows Release 使用说明

## 发布产物

- 安装版：`youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`
- 便携版：`youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`

两个产物都会内置：

- Python runtime
- Web 工作台
- `yt-dlp`
- `ffmpeg`
- `ffprobe`

普通用户不需要额外安装 Python、conda、`yt-dlp` 或 `ffmpeg`。

## 启动方式

- 安装版：安装后从开始菜单或桌面快捷方式启动
- 便携版：解压后双击 `youtube-downloader.exe`

启动器会自动完成下面几件事：

1. 启动本地后台服务 `youtube-downloader-service.exe`
2. 等待 `/api/health` 就绪
3. 自动打开默认浏览器并进入本地工作台

如果检测到已有本地服务正在运行，启动器会直接复用现有服务并打开浏览器。

## 当前运行时基线

当前 Windows release 与开发态使用同一套运行时基线：

- Web 后端：FastAPI + Uvicorn
- Agent runtime：LangGraph
- 后端业务能力：仓库内 `app/core/`、`app/tools/`、`app/agent/`

依赖边界约定如下：

- `requirements.txt`
  - 运行时共同基线，包含 `langgraph`、`fastapi`、`uvicorn` 等实际运行依赖
- `requirements-dev.txt`
  - 本地开发与测试入口，在 `requirements.txt` 基础上补充开发依赖
- `requirements-release.txt`
  - 仅包含打包额外依赖，例如 `pyinstaller`

开发、测试、打包默认统一使用 Miniconda `base` 环境。

## 开发者构建

```powershell
conda run -n base python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1
```

构建脚本会先安装运行时与打包依赖，然后执行一组 baseline tests，再进入 PyInstaller 打包。

当前 baseline tests 至少包括：

- `test_app_paths.py`
- `test_release_launcher.py`
- `test_release_runtime.py`
- `test_web_agent_runtime_api.py`
- `test_web_workspace_smoke.py`

PyInstaller spec 已显式纳入 `langgraph` 子模块，避免 release 包缺失运行时依赖。

## 版本与 changelog 流程

发布前按下面的顺序更新：

1. 修改仓库根目录 `VERSION`
2. 更新 `CHANGELOG.md`
3. 运行 `.\scripts\build_windows_release.ps1`
4. 完成 smoke 验收
5. 创建并推送 `vX.Y.Z` tag

GitHub Actions 会在构建前校验 tag 与 `VERSION` 是否一致，不一致会直接失败。

## 发布前 Smoke Checklist

建议发布前至少完成下面这组 smoke：

1. 运行 `.\scripts\build_windows_release.ps1`
2. 确认 baseline tests 全部通过
3. 启动便携版或安装版，确认启动器能拉起后台服务
4. 确认浏览器能自动打开本地工作台
5. 确认 `/api/health` 返回 `200`
6. 确认 `/api/agent/plan` 可用
7. 至少手动验证一次搜索、计划、确认下载的主链路

## 默认目录

- 下载目录：`%USERPROFILE%\Downloads\YouTube Downloader`
- 应用数据：`%LOCALAPPDATA%\YouTube Downloader`
- 日志与运行时状态：`%LOCALAPPDATA%\YouTube Downloader\logs` 和 `%LOCALAPPDATA%\YouTube Downloader\runtime`

## 排障提示

如果 release 包启动失败，优先检查：

- `AppData\Local\YouTube Downloader\logs\web-service.log`
- `AppData\Local\YouTube Downloader\runtime\web-runtime.json`

常见问题：

- 启动器未打开浏览器
  - 先确认后台服务是否已经启动，再手动访问 `http://127.0.0.1:<port>`
- 后台服务未启动
  - 先看 `web-service.log` 是否存在导入错误、端口占用或依赖缺失
- Agent 接口可见但执行异常
  - 先确认 release 包来自最新构建，并确认 `langgraph` 已被正确打进 PyInstaller 产物

## 已知限制

- 当前只提供 Windows x64 发布物
- 首版未做代码签名，Windows Defender / SmartScreen 可能提示“未知发布者”
- 本地后台服务在无页面/API 活动且无后台任务持续 15 分钟后会自动退出

## GitHub 发布

- 推送 `vX.Y.Z` tag 后，GitHub Actions 会自动构建
- Release 资产会自动附加到对应 GitHub Release

## 本地产物保留建议

- GitHub Release 作为历史版本产物的长期归档位置
- 本地 `build/release/` 默认只保留当前正在验收或刚发布的版本
- 新版本验收完成后，可以删除旧版本的本地 zip / setup / portable 目录
- `ffmpeg-release-essentials.zip`、`ffmpeg-release-test/` 等临时构建产物不建议长期保留
