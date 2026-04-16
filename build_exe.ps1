$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot
$appName = "YouTubeVideoDownloader_portable"

Write-Host "[1/2] 检查 PyInstaller..."
python -m pip show pyinstaller | Out-Null

Write-Host "[2/2] 开始打包 GUI..."
python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onedir `
  --add-data "$PSScriptRoot\\myvi_yt_batch.py;." `
  --name $appName `
  "$PSScriptRoot\\gui_app.py"

Write-Host ""
Write-Host "打包完成: $PSScriptRoot\\dist\\$appName.exe"
