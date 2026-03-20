# Contributing Guide

感谢你为本项目做贡献。

## 1. 开发环境

```powershell
cd D:\YTBDLP
python -m pip install -U -r requirements.txt
python gui_app.py
```

## 2. 分支与提交规范

- 从 `main` 拉新分支进行开发
- 分支命名建议：
  - `feat/<short-name>`
  - `fix/<short-name>`
  - `docs/<short-name>`
- 提交信息建议：
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `refactor: ...`

## 3. Pull Request 要求

提交 PR 时请尽量包含：

- 变更目的与背景
- 主要修改点（GUI / 后端 / 打包）
- 手工验证步骤
- 截图（若涉及 UI）
- 兼容性说明（Python 版本、Windows 版本）

## 4. 代码风格

- 默认使用 UTF-8 编码
- 变量命名清晰，避免过短缩写
- 复杂逻辑添加简短注释
- 避免提交临时文件、构建产物与下载数据

## 5. Issue 报告建议

请在 Issue 中附上：

- 运行命令或操作步骤
- 完整报错日志（不要只截一行）
- 使用版本（`yt-dlp` / `ffmpeg` / Python）
- 系统信息（Windows 版本）

## 6. 不建议提交的内容

- `dist/`、`build/` 打包产物
- `downloads/`、`video_info/` 运行数据
- 本地配置或缓存文件

## 7. 安全与合规

请确保贡献内容遵守相关法律法规和平台条款，不得用于侵权或非法用途。

