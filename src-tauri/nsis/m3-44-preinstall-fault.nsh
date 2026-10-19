; M3-44 ONLY: simulate a deterministic failure BEFORE any installed files,
; registry values or shortcuts are written. This file must never be
; referenced from ordinary release configurations.
;
; Reuse the exact existing user-data preservation hook (no model removal).
!include "${__FILEDIR__}\preserve-data.nsh"

!macro NSIS_HOOK_PREINSTALL
  ReadEnvStr $R9 "AIIMAGE_M3_44_ABORT_PREINSTALL"
  StrCmp $R9 "1" 0 m3_44_preflight_ok
  SetErrorLevel 83
  Quit
  m3_44_preflight_ok:
!macroend
