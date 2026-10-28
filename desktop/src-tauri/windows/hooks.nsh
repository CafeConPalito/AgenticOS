; Agentic OS installer look (phase 20, amendment 1). This file is included before the pages,
; so the MUI defines below apply to them: the main theme's navy (the app's --sidebar token, see
; scripts/installer_art.py) for the header and the welcome and finish pages, the authorship as
; in the app's About page, and the license page asking for acceptance.
!define MUI_BGCOLOR "0F2347"
!define MUI_TEXTCOLOR "FFFFFF"
!define MUI_WELCOMEPAGE_TITLE "Agentic OS"
!define MUI_WELCOMEPAGE_TEXT "Te damos la bienvenida al instalador de Agentic OS, el orquestador de agentes de IA.$\r$\n$\r$\nAgentic OS es software libre bajo la licencia GNU GPLv3: en el siguiente paso podrás leerla y tendrás que aceptarla para continuar.$\r$\n$\r$\nMade By Café Con Palito with ❤$\r$\nAlbano Díez de Paulino"
!define MUI_LICENSEPAGE_TEXT_TOP "Para instalar Agentic OS debes aceptar la licencia GNU GPLv3."
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "He leído y acepto los términos de la licencia"
!define MUI_FINISHPAGE_TITLE "Agentic OS está instalado"
!define MUI_FINISHPAGE_TEXT "Ya puedes empezar a orquestar tus agentes.$\r$\n$\r$\nMade By Café Con Palito with ❤$\r$\nAlbano Díez de Paulino"

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
