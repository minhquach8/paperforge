[Setup]
AppName=Paperforge Student
AppVersion=1.0.0
DefaultDirName={pf}\Paperforge Student
DefaultGroupName=Paperforge
OutputDir=dist
OutputBaseFilename=Paperforge-Student-Setup
ArchitecturesInstallIn64BitMode=x64
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\Paperforge Student\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Paperforge Student"; Filename: "{app}\Paperforge Student.exe"
Name: "{commondesktop}\Paperforge Student"; Filename: "{app}\Paperforge Student.exe"

[Run]
Filename: "{app}\Paperforge Student.exe"; Flags: nowait postinstall skipifsilent
