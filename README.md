# YouTube Agent Downloader

一个基于 `yt-dlp` 的本地 Agent 下载器，正在从旧版桌面 GUI 迁移到前后端分离的网页模式。

当前目标：

- 在浏览器中输入自然语言任务
- 由本地 Agent 规划搜索、筛选与下载步骤
- 通过本地后端 API 执行任务，而不是依赖 EXE 界面
- 保留原有 CLI / 核心下载能力作为迁移基础

## 当前产品方向

- Web 工作台是默认本地入口
- `app/web/main.py`
  - 新的本地 Web 后端入口
- `app/web/static/index.html`
  - 新的浏览器工作台壳
- `gui_app.py`
  - 旧版桌面 GUI，作为 legacy 兼容入口与迁移参考，不再是默认产品壳

## 项目结构

```text
D:\YTBDLP
├─ app/
│  ├─ agent/                  # Agent planner / runner
│  ├─ core/                   # 可复用搜索、筛选、下载能力
│  ├─ tools/                  # 工具层
│  └─ web/                    # Web API 与前端壳
├─ gui_app.py                 # 旧桌面 GUI（迁移参考）
├─ youtube_batch.py           # 兼容 CLI 入口
├─ requirements.txt
└─ ...
```

## 环境要求

- Windows 10/11
- Python 3.10+（推荐 3.12）
- ffmpeg（建议加入 PATH）

## 安装与运行

默认启动方式：

```powershell
cd <repo-dir>
.\run_web.bat
```

脚本会优先使用 conda 环境启动本地 Web 服务，默认环境名为 `base`，可通过环境变量 `YTBDLP_CONDA_ENV` 覆盖。

如果需要手动执行：

```powershell
cd <repo-dir>
conda run -n base python -m pip install -U -r requirements.txt
conda run -n base python -m uvicorn --app-dir . app.web.main:app --reload --host 127.0.0.1 --port 8000
```

或直接使用启动脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_web.ps1
```

打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 迁移状态

- Web 后端：默认本地入口
- 浏览器前端：默认工作台
- 桌面 GUI：冻结为 legacy compatibility path，仅保留迁移期参考和必要兼容修复

## CLI 兼容

旧 CLI 入口仍保留，便于迁移期间继续验证核心能力，但不再承担默认用户入口职责。

## 测试基线

当前前端自动化只保留最小 smoke 基线，不扩张成高成本 UI 自动化体系。优先保护的是 Web 工作台主链路是否还能正常渲染和完成关键交互。

推荐基线命令：

```powershell
cd <repo-dir>
conda run -n base python -m unittest discover -s tests -p "test_web_workspace_smoke.py"
```

如涉及 Web API / 状态流改动，再补对应后端契约测试，而不是优先增加重型前端 UI 自动化。

## 免责声明

本项目仅用于合法、合规的内容获取与研究用途。  
请遵守 YouTube 服务条款及所在司法辖区法律法规，不得用于侵权或非法用途。

## License

建议使用 MIT License（可在仓库中添加 `LICENSE` 文件）。
