# YouTube 视频下载工具（yt-dlp GUI）

一个基于 `yt-dlp + PySide6` 的桌面工具，支持：
- 在工具内输入查询词，检索 YouTube 视频并抓取元数据
- 按规则筛选可下载 URL 并形成任务队列
- 并发下载、断点续跑、失败重试、下载报告导出
- 直观的队列执行界面与实时进度展示

适合批量采集与下载场景。

## 功能特性

### 1) 检索与筛选
- 单行查询词输入（类似 YouTube 搜索框）
- 可配置视频收集条数、最短时长、上传年份范围
- 元数据抓取并发可调（加速第 2 步）
- 生成标准中间文件：候选、筛选结果、URL 列表

### 2) 队列与下载
- 任务队列管理（启动筛选、下载选中、下载全部、恢复未完成）
- 并发视频下载（最多 8）+ 分片并发
- 失败 URL 自动记录并支持重试
- SponsorBlock 清理（可选类别）
- 字幕策略：不下载/不嵌入独立字幕轨，硬字幕不处理

### 3) 进度与结果
- 实时进度：元数据抓取进度、队列进度、当前视频进度
- 并发任务卡片（每线程进度、已下载大小、速度）
- 下载结果报告 `07_download_report.csv`（UTF-8 BOM，Excel 友好）
- 报告字段精简为：
  - `video_id`
  - `title`
  - `watch_url`
  - `失败原因`
  - `上传时间`

### 4) 工具维护
- 检查 `yt-dlp / ffmpeg` 当前版本与更新状态
- 一键更新 `yt-dlp`
- 一键更新 `ffmpeg`（优先 winget，回退 choco）

## 项目结构

```text
D:\YTBDLP
├─ gui_app.py                 # GUI 主程序
├─ myvi_yt_batch.py           # 检索/筛选/下载后端
├─ build_exe.ps1              # 打包脚本（PyInstaller）
├─ requirements.txt           # 依赖
├─ UPDATELOG.md               # 更新日志
└─ ...
```

## 环境要求

- Windows 10/11
- Python 3.10+（推荐 3.12）
- ffmpeg（建议加入 PATH）

## 安装与运行（源码模式）

```powershell
cd D:\YTBDLP
python -m pip install -U -r requirements.txt
python gui_app.py
```

## 打包 EXE（分发给他人）

### 一键打包
```powershell
powershell -ExecutionPolicy Bypass -File D:\YTBDLP\build_exe.ps1
```

### 产物位置
- `D:\YTBDLP\dist\YouTubeVideoDownloader_portable\`

> 注意：目录版发布时，必须连同 `_internal` 一起分发，不能只拷贝单个 exe。

## 典型工作流

1. 在「任务配置」输入查询词并设置筛选参数  
2. 点击「启动筛选队列」生成并执行筛选任务  
3. 在「队列执行」加载视频列表，勾选目标视频  
4. 点击「下载勾选视频」或「下载选中任务」  
5. 下载结束后查看报告 `07_download_report.csv`

## CLI 用法（可选）

### 仅筛选（不下载）
```powershell
python myvi_yt_batch.py `
  --query-text "Perodua Myvi" `
  --workdir D:\YTBDLP\video_info `
  --search-limit 50 `
  --metadata-workers 4 `
  --min-duration 10 `
  --year-from 2020
```

### 从 URL 文件直接下载
```powershell
python myvi_yt_batch.py `
  --workdir D:\YTBDLP\video_info\run_xxx `
  --download-dir D:\YTBDLP\downloads `
  --download-from-urls-file D:\YTBDLP\video_info\run_xxx\05_selected_urls.txt `
  --download `
  --concurrent-videos 5 `
  --concurrent-fragments 8
```

## 常见问题（FAQ）

### 1. 启动慢
- 首次启动会加载 Qt 组件并进行工具探测，属正常现象
- 当前版本已将版本检查改为后台异步，体感已优化

### 2. `No video formats found`
- 常见于地区限制、账号/风控、源视频下架、访问受限
- 建议尝试：
  - 降低并发
  - 切换网络
  - 使用 `cookies-from-browser`
  - 重试失败 URL

### 3. 打包版找不到 Python
- 打包版执行后端任务仍依赖系统 Python（当前实现）
- 若目标机器无 Python，请先安装 Python 3.10+

## 开源计划（Roadmap）

- [ ] 无 Python 依赖的纯打包版（后端内置）
- [ ] 失败原因分类更细粒度与可视化统计
- [ ] 下载任务历史中心（检索/筛选/下载全链路）
- [ ] 多源镜像与网络诊断助手

## 免责声明

本项目仅用于合法、合规的内容获取与研究用途。  
请遵守 YouTube 服务条款及所在司法辖区法律法规，不得用于侵权或非法用途。

## License

建议使用 MIT License（可在仓库中添加 `LICENSE` 文件）。

