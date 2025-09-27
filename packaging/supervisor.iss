[Setup]
AppName=Paperforge Supervisor
AppVersion=1.0.0
DefaultDirName={pf}\Paperforge Supervisor
DefaultGroupName=Paperforge
OutputDir=dist
OutputBaseFilename=Paperforge-Supervisor-Setup
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\Paperforge Supervisor\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Paperforge Supervisor"; Filename: "{app}\Paperforge Supervisor.exe"
Name: "{commondesktop}\Paperforge Supervisor"; Filename: "{app}\Paperforge Supervisor.exe"

[Run]
Filename: "{app}\Paperforge Supervisor.exe"; Flags: nowait postinstall skipifsilent
