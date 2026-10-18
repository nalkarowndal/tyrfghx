; Models and output files are user-owned, outside the installer payload.
; Tauri's stock UI has a delete-app-data checkbox. Override it even if selected.
!macro NSIS_HOOK_PREUNINSTALL
  StrCpy $DeleteAppDataCheckboxState 0
!macroend
