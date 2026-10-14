; Packs dist\Shtorka into dist\ShtorkaSetup.exe; build.ps1 passes the version.
; Installs for the current user only, so it never asks for administrator rights.

[Setup]
AppId={{6B0C1C5E-8C0B-4E3B-9C56-3F1B6C2A7D41}
AppName=Shtorka
AppVersion={#Version}
AppPublisher=team-kontora
AppPublisherURL=https://github.com/team-kontora/shtorka
DefaultDirName={localappdata}\Programs\Shtorka
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
CloseApplications=no
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=ShtorkaSetup
SetupIconFile=build\shtorka.ico
UninstallDisplayIcon={app}\Shtorka.exe
VersionInfoVersion={#Version}
VersionInfoProductName=Shtorka
VersionInfoDescription=Shtorka Setup

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[InstallDelete]
; files of the previous version that the new one no longer has
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\Shtorka\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Shtorka"; Filename: "{app}\Shtorka.exe"

[Run]
Filename: "{app}\Shtorka.exe"; Parameters: "--welcome"; Description: "{cm:LaunchProgram,Shtorka}"; Flags: nowait postinstall skipifsilent
; an update runs Setup silently and expects the app back afterwards
Filename: "{app}\Shtorka.exe"; Flags: nowait; Check: WizardSilent

[Registry]
; the app writes its autostart entry itself; uninstalling takes it away
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Shtorka"; Flags: dontcreatekey uninsdeletevalue

[Code]
procedure StopApp();
var
  Attempt, ExitCode: Integer;
begin
  // a copy that updates itself starts Setup and then quits; give it time before forcing it
  for Attempt := 1 to 25 do
  begin
    if not CheckForMutexes('ShtorkaAppMutex') then
      Exit;
    Sleep(200);
  end;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Shtorka.exe', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Sleep(500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  StopApp();
  Result := True;
end;
