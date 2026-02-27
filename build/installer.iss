; Inno Setup Script — FromSoft Mod Manager Installer
; Requires Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
; Run after build.py produces the dist/FromSoftModManager folder.

#define AppName "FromSoft Mod Manager"
#ifndef AppVersion
  #include "_version.iss"
#endif
#define AppPublisher "FromSoftModManager"
#define AppURL "https://github.com/spikehockey75/FromSoftModManager"
#define AppExeName "FromSoftModManager.exe"
#define SourceDir "..\dist\FromSoftModManager"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={localappdata}\FromSoftModManager
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=FromSoftModManager_Setup_v{#AppVersion}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern
SetupIconFile=..\resources\icons\fsmm.ico
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=force
CloseApplicationsFilter={#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config.json"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Detect existing install and show upgrade prompt
function InitializeSetup(): Boolean;
var
  PrevVersion: AnsiString;
  VersionFile: String;
begin
  Result := True;
  VersionFile := ExpandConstant('{localappdata}\FromSoftModManager\VERSION');
  if FileExists(VersionFile) then
  begin
    LoadStringFromFile(VersionFile, PrevVersion);
    PrevVersion := Trim(PrevVersion);
    if PrevVersion <> '' then
    begin
      Result := (MsgBox(
        '{#AppName} v' + PrevVersion + ' is already installed.' + #13#10 +
        'Update to v{#AppVersion}?',
        mbConfirmation, MB_YESNO) = IDYES);
    end;
  end;
end;

// Download and install ME3 if not already present
procedure DownloadME3();
var
  ME3Dir: String;
begin
  ME3Dir := ExpandConstant('{localappdata}\me3');
  if not DirExists(ME3Dir) then
  begin
    if MsgBox('Mod Engine 3 (ME3) is required for game launching.' + #13#10 +
              'Download and install ME3 now?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      // ME3 will be downloaded by the app itself on first launch
      MsgBox('ME3 will be downloaded automatically when you first launch the app.', mbInformation, MB_OK);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    DownloadME3();
  end;
end;

// Prompt to remove user data (config, mods) on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    AppDir := ExpandConstant('{app}');
    if DirExists(AppDir) then
    begin
      if MsgBox('Delete your settings and downloaded mods?' + #13#10 +
                'This will remove everything in:' + #13#10 +
                AppDir, mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(AppDir, True, True, True);
      end;
    end;
  end;
end;
