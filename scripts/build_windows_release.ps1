param(
    [string]$Version = "0.1.0",
    [string]$PythonExe = "",
    [string]$IsccExe = "",
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VendorDir = Join-Path $Root "vendor\bin"
$BuildDir = Join-Path $Root "build\release"
$PortableDir = Join-Path $BuildDir ("portable\youtube-downloader-web-v{0}-win-x64" -f $Version)
$PortableZip = Join-Path $BuildDir ("youtube-downloader-web-v{0}-win-x64-portable.zip" -f $Version)
$LauncherDist = Join-Path $Root "dist\youtube-downloader"
$ServiceDist = Join-Path $Root "dist\youtube-downloader-service"
$PyInstallerLauncherSpec = Join-Path $Root "packaging\pyinstaller\launcher.spec"
$PyInstallerServiceSpec = Join-Path $Root "packaging\pyinstaller\service.spec"
$InstallerScript = Join-Path $Root "packaging\windows\installer.iss"
$ReleaseNotes = Join-Path $Root "docs\WINDOWS_RELEASE.md"
$Requirements = Join-Path $Root "requirements.txt"
$ReleaseRequirements = Join-Path $Root "requirements-release.txt"

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Download([string]$Url, [string]$Destination) {
    Write-Step "Download $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Destination
}

function Get-RequiredTool([string]$Name) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "Missing required tool: $Name"
    }
    return $cmd.Source
}

function Resolve-ExistingPath([string]$PathValue, [string]$Label) {
    if (-not $PathValue) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $PathValue)) {
        throw "$Label does not exist: $PathValue"
    }
    return (Resolve-Path -LiteralPath $PathValue).Path
}

New-Item -ItemType Directory -Path $VendorDir -Force | Out-Null
New-Item -ItemType Directory -Path $BuildDir -Force | Out-Null
Remove-Item -LiteralPath $PortableDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $PortableDir -Force | Out-Null

$Python = Resolve-ExistingPath $PythonExe "PythonExe"
if (-not $Python) {
    $Python = Get-RequiredTool "python"
}

Write-Step "Install packaging dependencies"
& $Python -m pip install -U -r $Requirements -r $ReleaseRequirements

if (-not $SkipTests) {
    Write-Step "Run baseline tests"
    & $Python -m unittest discover -s (Join-Path $Root "tests") -p "test_app_paths.py"
    & $Python -m unittest discover -s (Join-Path $Root "tests") -p "test_web_workspace_smoke.py"
}

$YtDlpExe = Join-Path $VendorDir "yt-dlp.exe"
$FfmpegZip = Join-Path $BuildDir "ffmpeg-release-essentials.zip"
$FfmpegExtract = Join-Path $BuildDir "ffmpeg-release"

Invoke-Download "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" $YtDlpExe
Invoke-Download "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $FfmpegZip

Remove-Item -LiteralPath $FfmpegExtract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $FfmpegZip -DestinationPath $FfmpegExtract -Force
$FfmpegBin = Get-ChildItem -Path $FfmpegExtract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
$FfprobeBin = Get-ChildItem -Path $FfmpegExtract -Recurse -Filter "ffprobe.exe" | Select-Object -First 1
if (-not $FfmpegBin -or -not $FfprobeBin) {
    throw "Could not find ffmpeg.exe / ffprobe.exe in extracted archive"
}
Copy-Item -LiteralPath $FfmpegBin.FullName -Destination (Join-Path $VendorDir "ffmpeg.exe") -Force
Copy-Item -LiteralPath $FfprobeBin.FullName -Destination (Join-Path $VendorDir "ffprobe.exe") -Force

Write-Step "Build launcher"
& $Python -m PyInstaller --noconfirm --clean $PyInstallerLauncherSpec

Write-Step "Build background service"
& $Python -m PyInstaller --noconfirm --clean $PyInstallerServiceSpec

Write-Step "Assemble portable directory"
Copy-Item -Path (Join-Path $LauncherDist "*") -Destination $PortableDir -Recurse -Force
Copy-Item -Path (Join-Path $ServiceDist "*") -Destination $PortableDir -Recurse -Force
New-Item -ItemType Directory -Path (Join-Path $PortableDir "vendor\bin") -Force | Out-Null
Copy-Item -Path (Join-Path $VendorDir "*") -Destination (Join-Path $PortableDir "vendor\bin") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $PortableDir "README.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "LICENSE") -Destination (Join-Path $PortableDir "LICENSE") -Force
if (Test-Path -LiteralPath $ReleaseNotes) {
    Copy-Item -LiteralPath $ReleaseNotes -Destination (Join-Path $PortableDir "WINDOWS_RELEASE.md") -Force
}

if (Test-Path -LiteralPath $PortableZip) {
    Remove-Item -LiteralPath $PortableZip -Force
}
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $PortableZip -CompressionLevel Optimal

if (-not $SkipInstaller) {
    $ResolvedIscc = Resolve-ExistingPath $IsccExe "IsccExe"
    if (-not $ResolvedIscc) {
        $Iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
        if ($Iscc) {
            $ResolvedIscc = $Iscc.Source
        }
    }
    if (-not $ResolvedIscc) {
        throw "Could not find iscc.exe. Install Inno Setup or use -SkipInstaller."
    }
    Write-Step "Build setup installer"
    & $ResolvedIscc "/DAppVersion=$Version" "/DSourceDir=$PortableDir" "/DOutputDir=$BuildDir" $InstallerScript
}

Write-Step "Done"
Write-Host "Portable: $PortableZip"
