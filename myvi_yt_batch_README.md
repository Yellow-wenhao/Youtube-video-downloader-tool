# YouTube 车型类视频：搜索筛选与批量下载

基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp)：`ytsearch:` 搜索、`--flat-playlist` / `--dump-single-json` 拉元数据，下载侧使用 `--download-archive`、`--write-info-json` 等。  
**「是否实车画面」无法仅靠元数据 100% 判定**，入选后请人工抽查。

## 流程概要

1. 准备关键词列表（每行一条搜索词，可换任意车型）
2. yt-dlp 搜索候选
3. 按 video id 去重
4. 逐条拉详细元数据
5. Python 本地规则打分（车型短语 + 介绍意图词 + 排除词 + 时长 + 直播/可用性 + 可选年份）
6. 导出 CSV / URL，确认后 `--download`

## 安装

```bash
python -m pip install -U -r requirements.txt
```

建议安装 **ffmpeg** 并加入 PATH，便于合并音视频。

## 图形界面（GUI）

安装依赖后可直接启动：

```bash
python gui_app.py
```

GUI 提供：
- 参数表单：关键词文件、工作/下载目录、车型短语、搜索条数、最短时长、按年筛选、语言规则、cookies
- 分页布局：`任务配置` / `队列与执行` / `日志与结果`
- 新工作流：先“筛选并提取 URL”形成队列，再在“队列与执行”触发下载
- 操作按钮：配置页仅做“加入筛选队列”；队列页支持启动筛选队列、下载选中任务、下载全部已筛选任务
- 实时进度：显示流程阶段（1/4~4/4）、当前视频下载百分比、下载速度、已下载大小/总大小
- 实时日志：展示脚本标准输出
- 结果预览：自动载入并预览 `04_selected_for_review.csv`
- 任务增强：支持任务队列、目录历史、参数预设保存/加载、日志右键复制/清空
- 下载设置：支持下载模式（video/audio）、视频封装格式、最大分辨率、码率上限、是否合并音频、音频格式与质量
- 工具维护：支持检查 `yt-dlp/ffmpeg` 版本，一键更新 `yt-dlp`，以及自动更新 `ffmpeg`（优先 winget，回退 choco）

## 常用命令

**只筛选、不下载**（先看出 CSV 质量）：

```bash
python myvi_yt_batch.py ^
  --query-file perodua_myvi_queries.txt ^
  --workdir ./myvi_dataset ^
  --vehicle-phrase "perodua myvi" ^
  --search-limit 50 ^
  --min-duration 120
```

**换车型示例**（关键词文件里写 Toyota Vios 相关搜索词）：

```bash
python myvi_yt_batch.py ^
  --query-file queries_vios.txt ^
  --workdir ./vios_dataset ^
  --vehicle-phrase "toyota vios" ^
  --search-limit 40 ^
  --min-duration 120
```

**按上传年份区间**（例如只要 2020–2024 年上传的）：

```bash
python myvi_yt_batch.py ^
  --query-file perodua_myvi_queries.txt ^
  --workdir ./myvi_2020_2024 ^
  --vehicle-phrase "perodua myvi" ^
  --year-from 2020 ^
  --year-to 2024 ^
  --full-csv
```

**确认后下载**：

```bash
python myvi_yt_batch.py ^
  --query-file perodua_myvi_queries.txt ^
  --workdir ./myvi_dataset ^
  --download-dir ./myvi_downloads ^
  --vehicle-phrase "perodua myvi" ^
  --search-limit 50 ^
  --min-duration 120 ^
  --download
```

**年龄/会员限制等**：可加 `--cookies-from-browser chrome` 或 `--cookies-file ...`。

## 输出文件（workdir 下）

| 文件 | 说明 |
|------|------|
| `01_search_candidates.jsonl` | 搜索原始候选 |
| `02_detailed_candidates.jsonl` | 详细元数据 |
| `03_scored_candidates.jsonl` | 打分后全量 |
| `04_selected_for_review.csv` | **入选**待人工复核 |
| `04_all_scored.csv` | 加 `--full-csv` 时写出，**全部候选**打分行 |
| `05_selected_urls.txt` | 入选 URL，供下载 |
| `download_archive.txt` | 下载去重归档（与 `--download` 同用） |

## 主要参数

| 参数 | 说明 |
|------|------|
| `--query-file` | 关键词文件；省略则用脚本内置默认 Myvi 搜索词表 |
| `--vehicle-phrase` | 标题/描述/标签须命中的车型短语，如 `perodua myvi`、`honda city` |
| `--min-duration` | 最短时长（秒），过短降分且通常不入选 |
| `--search-limit` | 每个关键词取几条搜索结果 |
| `--year-from` / `--year-to` | 上传年份上下限（无 upload_date 则该条不入选） |
| `--lang-rules` | `en` 仅英文意图词，`my` 仅马来补充，`both` 合并（默认） |
| `--full-csv` | 额外输出全量打分 CSV |
| `--download` | 对入选 URL 下载 |
| `--yt-extra-args` | 透传给 yt-dlp 的附加参数字符串，如代理/重试/限速等 |
| `--download-from-urls-file` | 仅下载模式：从 URL 文件读取链接直接下载（不重新筛选） |
| `--download-mode` | 下载模式：`video` 或 `audio` |
| `--include-audio` / `--no-include-audio` | 视频模式是否合并音频 |
| `--video-container` | 视频封装偏好：`auto/mp4/mkv/webm` |
| `--max-height` | 视频最大分辨率高度（如 1080） |
| `--max-bitrate-kbps` | 视频总码率上限（kbps） |
| `--audio-format` | 音频模式输出格式：`best/mp3/m4a/opus/wav/flac` |
| `--audio-quality` | 音频质量 0-10（0 最佳） |

更细变更见仓库根目录 **UPDATELOG.md**。
