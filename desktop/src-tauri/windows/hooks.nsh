; Agentic OS installer hooks (phase 08, ADR 0012).
;
; The uninstaller's «Delete the application data» checkbox only removes the folders named
; after the bundle identifier. Our data lives in %APPDATA%\AgenticOS (database, logs, the
; pointer to a moved data folder): remove it too when the box is checked, never on an update.
; A data folder the user moved elsewhere is left in place (the README says so).
!macro NSIS_HOOK_POSTUNINSTALL
  ${If} $DeleteAppDataCheckboxState = 1
  ${AndIf} $UpdateMode <> 1
    SetShellVarContext current
    RMDir /r "$APPDATA\AgenticOS"
  ${EndIf}
!macroend
