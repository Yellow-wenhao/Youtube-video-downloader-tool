# Release Checklist

用于每次 Windows release 发版前后的最短操作清单。

## 1. 更新版本信息

1. 修改仓库根目录 `VERSION`
2. 更新 [CHANGELOG.md](./CHANGELOG.md)
3. 确认需要发布的 tag 名为 `vX.Y.Z`

## 2. 本地构建

```powershell
conda run -n base python -m pip install -U -r requirements.txt -r requirements-release.txt
.\scripts\build_windows_release.ps1
```

确认生成：

- `build/release/youtube-downloader-web-vX.Y.Z-win-x64-portable.zip`
- `build/release/youtube-downloader-web-vX.Y.Z-win-x64-setup.exe`

## 3. 最小 smoke

至少人工确认一次：

1. 启动安装版或便携版
2. 浏览器自动打开本地工作台
3. `/api/health` 返回 `200`
4. `/api/agent/plan` 可用
5. 完成一次搜索 -> 计划 -> 确认下载主链路

## 4. 提交与发布

```powershell
git status
git add VERSION CHANGELOG.md docs/RELEASE_CHECKLIST.md
git add README.md docs/WINDOWS_RELEASE.md .github/workflows/windows-release.yml scripts/build_windows_release.ps1
git commit -m "release: prepare vX.Y.Z"
git tag vX.Y.Z
git push origin <branch>
git push origin vX.Y.Z
```

## 5. GitHub Release 核对

确认 GitHub Actions 成功后，检查对应 Release：

1. tag 名正确
2. 资产已上传
3. 安装版和便携版都存在
4. Release 标题和自动说明正常

## 6. 本地产物保留策略

默认采用下面这条简单规则：

1. GitHub Release 是历史版本产物的唯一长期归档位置
2. 仓库本地 `build/release/` 只保留当前正在验收或刚完成发布的版本
3. 上一个版本的本地 zip / setup / portable 目录在新版本验收通过后即可删除
4. `ffmpeg-release-essentials.zip`、`ffmpeg-release-test/` 之类临时构建产物不作为发布资产保留

也就是说：

- 要追溯历史版本，去 GitHub Release
- 要做当前版本验收，留本地最新一版即可
- 不建议长期在工作区堆积多个历史二进制版本

## 7. 出问题时先看哪里

- `build/release/`
- `docs/WINDOWS_RELEASE.md`
- `%LOCALAPPDATA%\YouTube Downloader\logs\web-service.log`
- `%LOCALAPPDATA%\YouTube Downloader\runtime\web-runtime.json`
