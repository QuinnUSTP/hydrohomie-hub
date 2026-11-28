#define AppName "HydroHomie Control Center"
#define AppVersion "0.1.0"

[Setup]
AppId={{74CAF9FF-2A6B-4119-8A26-4E2429991CF7}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=HydroHomie
DefaultDirName={autopf}\HydroHomie
DefaultGroupName=HydroHomie
OutputDir=..\dist
OutputBaseFilename=HydroHomie-Setup-{#AppVersion}
SetupIconFile=..\build\hydrohomie.ico
UninstallDisplayIcon={app}\hydrohomie.ico
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Dirs]
Name: "{commonappdata}\HydroHomie"; Permissions: users-modify

[Files]
Source: "..\build\stage\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\stage\app\*"; DestDir: "{app}\app"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\hydrohomie.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m desktop.app"; WorkingDir: "{app}\app"; IconFilename: "{app}\hydrohomie.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m desktop.app"; WorkingDir: "{app}\app"; IconFilename: "{app}\hydrohomie.ico"

[Registry]
Root: HKA; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HydroHomie"; ValueData: """{app}\python\pythonw.exe"" -m desktop.app --background"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m desktop.app"; WorkingDir: "{app}\app"; Description: "Start HydroHomie now"; Flags: nowait postinstall skipifsilent

[Code]
procedure StopHydroHomie;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like ''' + ExpandConstant('{app}') + '\python\*'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopHydroHomie;
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopHydroHomie;
end;