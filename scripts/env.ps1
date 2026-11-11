# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
# Keep every uv artefact (uv itself, the Python build, the package cache, the venv) inside this folder.
# Dot-source this before calling .uv\uv.exe. Nothing is written to %LOCALAPPDATA%, %APPDATA% or PATH.
$env:UV_PYTHON_INSTALL_DIR  = "$PSScriptRoot\.python"
$env:UV_CACHE_DIR           = "$PSScriptRoot\.uv-cache"
$env:UV_PROJECT_ENVIRONMENT = "$PSScriptRoot\.venv"
$env:UV_PYTHON_PREFERENCE   = "only-managed"   # never pick up a Python installed elsewhere on the machine
$env:UV_NO_MODIFY_PATH      = "1"
$env:UV_TOOL_DIR            = "$PSScriptRoot\.uv-tools"
$env:UV_TOOL_BIN_DIR        = "$PSScriptRoot\.uv-tools\bin"
