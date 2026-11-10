; Inno Setup script for the Windows installer (iscc build\installer.iss after PyInstaller has built dist\StockScreener).
; Installs for the current user only, so no administrator rights are needed.
#ifndef AppVersion
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{6F0C3B2E-8C1D-4E43-9B5A-2D7E1C4F9A10}
AppName=Stock Screener
AppVersion={#AppVersion}
AppPublisher=Stock Screener (personal)
DefaultDirName={localappdata}\Programs\Stock Screener
DefaultGroupName=Stock Screener
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=StockScreener-Setup
SetupIconFile=..\app\icons\icon.ico
UninstallDisplayIcon={app}\StockScreener.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put an icon on the desktop"; GroupDescription: "Icons:"

[Files]
Source: "..\dist\StockScreener\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Stock Screener"; Filename: "{app}\StockScreener.exe"
Name: "{userdesktop}\Stock Screener"; Filename: "{app}\StockScreener.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StockScreener.exe"; Description: "Open Stock Screener now"; Flags: nowait postinstall skipifsilent
; an update installs silently and then opens the app again (the app's updater passes /RELAUNCH=1)
Filename: "{app}\StockScreener.exe"; Flags: nowait; Check: Relaunch

[Code]
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

[UninstallDelete]
; the program's own copy of the screener data and downloads; your journal ("StockScreener data") is never removed
Type: filesandordirs; Name: "{localappdata}\StockScreener\program"
