@echo off
rem Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
rem Same as run.ps1, for cmd / double-click:  run.cmd <test script> [arguments]
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
