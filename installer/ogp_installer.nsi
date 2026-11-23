; Open Garden Planner - NSIS Installer Script
; Build with: makensis /DVERSION=1.0.0 /DSRCDIR=dist\OpenGardenPlanner /DOUTDIR=dist \
;   /DLICENSE_FILE=LICENSE /DNOTICES_FILE=dist\THIRD_PARTY_NOTICES.md \
;   /DAPP_ICON=installer\ogp_app.ico /DFILE_ICON=installer\ogp_file.ico ogp_installer.nsi

;---------------------------------------------------------------------------
; Build-time defines (passed via /D flags from build_installer.py)
;---------------------------------------------------------------------------
; VERSION     - e.g. "1.0.0"
; SRCDIR      - PyInstaller output directory (dist\OpenGardenPlanner)
; OUTDIR      - Where to write the installer .exe
; LICENSE_FILE - Path to LICENSE (GPLv3)
; NOTICES_FILE - Path to THIRD_PARTY_NOTICES.md (generated from the frozen bundle)
; APP_ICON    - Path to application .ico
; FILE_ICON   - Path to .ogp file .ico

!ifndef VERSION
  !define VERSION "1.0.0"
!endif

; Third-party notices are generated from the frozen bundle by
; scripts/generate_distribution_inventory.py; build_installer.py always passes
; /DNOTICES_FILE. It is mandatory: a release whose notices are missing must fail
; the build, not ship an installer without them (AUD-051).
!ifndef NOTICES_FILE
  !error "NOTICES_FILE is not defined - pass /DNOTICES_FILE=<path to THIRD_PARTY_NOTICES.md>"
!endif
!if /FileExists "${NOTICES_FILE}"
!else
  !error "NOTICES_FILE does not exist: ${NOTICES_FILE}"
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

; Finish page
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"

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
!define MUI_LANGDLL_ALLLANGUAGES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "French"

; Modern UI translates the standard pages and buttons.
LangString OGP_MAIN ${LANG_ENGLISH} "${APP_NAME} (required)"
LangString OGP_DESKTOP ${LANG_ENGLISH} "Desktop shortcut"
LangString OGP_ASSOCIATION ${LANG_ENGLISH} ".ogp file association"
LangString OGP_MAIN_DESC ${LANG_ENGLISH} "Install the application (required)."
LangString OGP_DESKTOP_DESC ${LANG_ENGLISH} "Create a desktop shortcut."
LangString OGP_ASSOCIATION_DESC ${LANG_ENGLISH} "Open .ogp files on double-click."
LangString OGP_UPGRADE ${LANG_ENGLISH} "Click OK to uninstall the previous version of ${APP_NAME} and continue, or Cancel to quit."

LangString OGP_MAIN ${LANG_GERMAN} "${APP_NAME} (erforderlich)"
LangString OGP_DESKTOP ${LANG_GERMAN} "Desktopverknüpfung"
LangString OGP_ASSOCIATION ${LANG_GERMAN} ".ogp-Dateizuordnung"
LangString OGP_MAIN_DESC ${LANG_GERMAN} "Installiert das Programm (erforderlich)."
LangString OGP_DESKTOP_DESC ${LANG_GERMAN} "Erstellt eine Desktopverknüpfung."
LangString OGP_ASSOCIATION_DESC ${LANG_GERMAN} "Öffnet .ogp-Dateien per Doppelklick."
LangString OGP_UPGRADE ${LANG_GERMAN} "Klicken Sie auf OK, um die bisherige Version von ${APP_NAME} zu deinstallieren, oder auf Abbrechen."

LangString OGP_MAIN ${LANG_SPANISH} "${APP_NAME} (obligatorio)"
LangString OGP_DESKTOP ${LANG_SPANISH} "Acceso directo en el escritorio"
LangString OGP_ASSOCIATION ${LANG_SPANISH} "Asociación de archivos .ogp"
LangString OGP_MAIN_DESC ${LANG_SPANISH} "Instala la aplicación (obligatorio)."
LangString OGP_DESKTOP_DESC ${LANG_SPANISH} "Crea un acceso directo en el escritorio."
LangString OGP_ASSOCIATION_DESC ${LANG_SPANISH} "Abre archivos .ogp al hacer doble clic."
LangString OGP_UPGRADE ${LANG_SPANISH} "Pulsa Aceptar para desinstalar la versión anterior de ${APP_NAME} y continuar, o Cancelar para salir."

LangString OGP_MAIN ${LANG_RUSSIAN} "${APP_NAME} (обязательно)"
LangString OGP_DESKTOP ${LANG_RUSSIAN} "Ярлык на рабочем столе"
LangString OGP_ASSOCIATION ${LANG_RUSSIAN} "Ассоциация файлов .ogp"
LangString OGP_MAIN_DESC ${LANG_RUSSIAN} "Устанавливает программу (обязательно)."
LangString OGP_DESKTOP_DESC ${LANG_RUSSIAN} "Создаёт ярлык на рабочем столе."
LangString OGP_ASSOCIATION_DESC ${LANG_RUSSIAN} "Открывает файлы .ogp двойным щелчком."
LangString OGP_UPGRADE ${LANG_RUSSIAN} "Нажмите «ОК», чтобы удалить предыдущую версию ${APP_NAME} и продолжить, или «Отмена» для выхода."

LangString OGP_MAIN ${LANG_FRENCH} "${APP_NAME} (obligatoire)"
LangString OGP_DESKTOP ${LANG_FRENCH} "Raccourci sur le Bureau"
LangString OGP_ASSOCIATION ${LANG_FRENCH} "Association des fichiers .ogp"
LangString OGP_MAIN_DESC ${LANG_FRENCH} "Installe l’application (obligatoire)."
LangString OGP_DESKTOP_DESC ${LANG_FRENCH} "Crée un raccourci sur le Bureau."
LangString OGP_ASSOCIATION_DESC ${LANG_FRENCH} "Ouvre les fichiers .ogp par un double-clic."
LangString OGP_UPGRADE ${LANG_FRENCH} "Cliquez sur OK pour désinstaller la version précédente de ${APP_NAME} et continuer, ou sur Annuler pour quitter."

;---------------------------------------------------------------------------
; Upgrade: silently uninstall previous version before installing
;---------------------------------------------------------------------------
Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
  ReadRegStr $R0 HKLM "${UNINSTALL_REG_KEY}" "UninstallString"
  StrCmp $R0 "" done

  MessageBox MB_OKCANCEL|MB_ICONINFORMATION \
    "$(OGP_UPGRADE)" \
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
Section "!$(OGP_MAIN)" SecMain
  SectionIn RO  ; Required, cannot be deselected

  SetOutPath "$INSTDIR"

  ; Copy all files from PyInstaller bundle
  File /r "${SRCDIR}\*.*"

  ; Copy icon files for file association
  File "/oname=ogp_app.ico" "${APP_ICON}"
  File "/oname=ogp_file.ico" "${FILE_ICON}"

  ; GPLv3 text in the install directory alongside the third-party notices: the
  ; MUI license page only DISPLAYS it during the wizard, so without this line
  ; the "notices next to LICENSE" claim would be false on disk.
  File "/oname=LICENSE" "${LICENSE_FILE}"

  ; Third-party license notices (AUD-051): one consolidated file next to the
  ; GPLv3 LICENSE, generated from the frozen bundle's own metadata. The
  ; existence check above makes this a compile-time requirement.
  File "/oname=THIRD_PARTY_NOTICES.md" "${NOTICES_FILE}"

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

Section "$(OGP_DESKTOP)" SecDesktop
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\ogp_app.ico"
SectionEnd

Section "$(OGP_ASSOCIATION)" SecFileAssoc
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
  !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "$(OGP_MAIN_DESC)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(OGP_DESKTOP_DESC)"
  !insertmacro MUI_DESCRIPTION_TEXT ${SecFileAssoc} "$(OGP_ASSOCIATION_DESC)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;---------------------------------------------------------------------------
; Uninstaller
;---------------------------------------------------------------------------
Section "Uninstall"

  ; --- Preserve user .ogp plans before wiping the install dir (issue #199) ---
  ; Some users saved projects directly inside the install directory. Because an
  ; upgrade silently runs this uninstaller (see .onInit), RMDir /r would destroy
  ; them. Copy any top-level *.ogp files to the same folder the app now defaults
  ; to, so recovered plans appear right where users will look for them.
  StrCpy $R2 0                                      ; recovered-file counter
  FindFirst $R1 $R3 "$INSTDIR\*.ogp"
  StrCmp $R3 "" close_backup                        ; nothing to back up
  CreateDirectory "$DOCUMENTS\Open Garden Planner\Recovered Plans"
loop_backup:
  StrCmp $R3 "" close_backup
  CopyFiles /SILENT "$INSTDIR\$R3" "$DOCUMENTS\Open Garden Planner\Recovered Plans\$R3"
  IntOp $R2 $R2 + 1
  FindNext $R1 $R3
  Goto loop_backup
close_backup:
  FindClose $R1
  ; Inform the user. /SD IDOK auto-selects OK in silent mode so the silent
  ; upgrade uninstall (.onInit → ExecWait '... /S ...') never blocks on a modal.
  IntCmp $R2 0 done_backup
  MessageBox MB_OK|MB_ICONINFORMATION \
    "$R2 garden plan(s) found in the program folder were copied to:$\r$\n$DOCUMENTS\Open Garden Planner\Recovered Plans" \
    /SD IDOK
done_backup:

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

