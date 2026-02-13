; Open Garden Planner - NSIS Installer Script
; Build with: makensis /DVERSION=1.0.0 /DSRCDIR=dist\OpenGardenPlanner /DOUTDIR=dist /DLICENSE_FILE=LICENSE /DAPP_ICON=installer\ogp_app.ico /DFILE_ICON=installer\ogp_file.ico ogp_installer.nsi

;---------------------------------------------------------------------------
; Build-time defines (passed via /D flags from build_installer.py)
;---------------------------------------------------------------------------
; VERSION     - e.g. "1.0.0"
; SRCDIR      - PyInstaller output directory (dist\OpenGardenPlanner)
; OUTDIR      - Where to write the installer .exe
; LICENSE_FILE - Path to LICENSE (GPLv3)
; APP_ICON    - Path to application .ico
; FILE_ICON   - Path to .ogp file .ico

!ifndef VERSION
  !define VERSION "1.0.0"
!endif

;---------------------------------------------------------------------------
; General settings
;---------------------------------------------------------------------------
!define APP_NAME "Open Garden Planner"
!define APP_EXE "OpenGardenPlanner.exe"
!define APP_PUBLISHER "cofade"
!define APP_URL "https://github.com/cofade/open-garden-planner"
!define INSTALL_DIR "$PROGRAMFILES\${APP_NAME}"
!define UNINSTALL_REG_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${VERSION}"
OutFile "${OUTDIR}\OpenGardenPlanner-v${VERSION}-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "${UNINSTALL_REG_KEY}" "InstallLocation"
RequestExecutionLevel admin
SetCompressor /SOLID lzma
SetCompressorDictSize 64

; Includes
!include "MUI2.nsh"
!include "FileFunc.nsh"

;---------------------------------------------------------------------------
; Modern UI configuration
;---------------------------------------------------------------------------
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"

; Branding
!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

; Welcome page
!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APP_NAME} Setup"
!define MUI_WELCOMEPAGE_TEXT "This wizard will guide you through the installation of ${APP_NAME} v${VERSION}.$\r$\n$\r$\nOpen Garden Planner is a precision garden planning tool with CAD-like metric accuracy.$\r$\n$\r$\nClick Next to continue."

; Finish page
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APP_NAME}"

;---------------------------------------------------------------------------
; Installer pages
;---------------------------------------------------------------------------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${LICENSE_FILE}"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Language
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

;---------------------------------------------------------------------------
; Upgrade: silently uninstall previous version before installing
;---------------------------------------------------------------------------
Function .onInit
  ReadRegStr $R0 HKLM "${UNINSTALL_REG_KEY}" "UninstallString"
  StrCmp $R0 "" done

  MessageBox MB_OKCANCEL|MB_ICONINFORMATION \
    "${APP_NAME} is already installed.$\r$\n$\r$\nClick OK to uninstall the previous version and continue, or Cancel to abort." \
    IDOK uninst
  Abort

uninst:
  ; Run the existing uninstaller silently
  ExecWait '$R0 /S _?=$INSTDIR'
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

done:
FunctionEnd

;---------------------------------------------------------------------------
; Installer sections
;---------------------------------------------------------------------------
Section "!${APP_NAME} (required)" SecMain
  SectionIn RO  ; Required, cannot be deselected

  SetOutPath "$INSTDIR"

  ; Copy all files from PyInstaller bundle
  File /r "${SRCDIR}\*.*"

  ; Copy icon files for file association
  File "/oname=ogp_app.ico" "${APP_ICON}"
  File "/oname=ogp_file.ico" "${FILE_ICON}"

  ; Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; Start Menu shortcut
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\ogp_app.ico"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

  ; Add/Remove Programs registry entry
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "URLInfoAbout" "${APP_URL}"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "DisplayIcon" "$INSTDIR\ogp_app.ico"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "${UNINSTALL_REG_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKLM "${UNINSTALL_REG_KEY}" "NoModify" 1
  WriteRegDWORD HKLM "${UNINSTALL_REG_KEY}" "NoRepair" 1

  ; Estimate installed size (in KB)
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKLM "${UNINSTALL_REG_KEY}" "EstimatedSize" $0

SectionEnd

Section "Desktop shortcut" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\ogp_app.ico"
SectionEnd

Section ".ogp file association" SecFileAssoc
  ; Register .ogp extension
  WriteRegStr HKCR ".ogp" "" "OpenGardenPlanner.Project"
  WriteRegStr HKCR ".ogp" "Content Type" "application/x-ogp"

  ; Register file type
  WriteRegStr HKCR "OpenGardenPlanner.Project" "" "Open Garden Planner Project"
  WriteRegStr HKCR "OpenGardenPlanner.Project\DefaultIcon" "" "$INSTDIR\ogp_file.ico,0"
  WriteRegStr HKCR "OpenGardenPlanner.Project\shell" "" "open"
  WriteRegStr HKCR "OpenGardenPlanner.Project\shell\open" "" "Open with ${APP_NAME}"
  WriteRegStr HKCR "OpenGardenPlanner.Project\shell\open\command" "" '"$INSTDIR\${APP_EXE}" "%1"'

  ; Notify Windows of file association change
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0x0000, p 0, p 0)'
SectionEnd

;---------------------------------------------------------------------------
; Section descriptions
;---------------------------------------------------------------------------
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "Install ${APP_NAME} core files (required)."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "Create a shortcut on the desktop."
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFileAssoc} "Associate .ogp files with ${APP_NAME} so you can double-click to open them."
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;---------------------------------------------------------------------------
; Uninstaller
;---------------------------------------------------------------------------
Section "Uninstall"

  ; Remove files (entire install directory)
  RMDir /r "$INSTDIR"

  ; Remove Start Menu shortcuts
  RMDir /r "$SMPROGRAMS\${APP_NAME}"

  ; Remove desktop shortcut
  Delete "$DESKTOP\${APP_NAME}.lnk"

  ; Remove file association
  DeleteRegKey HKCR ".ogp"
  DeleteRegKey HKCR "OpenGardenPlanner.Project"

  ; Remove uninstall registry key
  DeleteRegKey HKLM "${UNINSTALL_REG_KEY}"

  ; Notify Windows of file association change
  System::Call 'shell32::SHChangeNotify(i 0x08000000, i 0x0000, p 0, p 0)'

SectionEnd

