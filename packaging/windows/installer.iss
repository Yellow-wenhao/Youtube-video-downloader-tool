#define MyAppName "YouTube Downloader"
#ifndef AppVersion
  #define AppVersion "0.1.4"
#endif
#ifndef SourceDir
  #define SourceDir "build\\release\\portable\\youtube-downloader-web-v" + AppVersion + "-win-x64"
#endif
#ifndef OutputDir
  #define OutputDir "build\\release"
#endif

[Setup]
AppId={{5A6E0714-DB76-4B7A-8FE2-4D3B2D3070F0}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=Yellow-wenhao
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename=youtube-downloader-web-v{#AppVersion}-win-x64-setup
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\youtube-downloader.exe

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\youtube-downloader.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\youtube-downloader.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\youtube-downloader.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\vendor"
