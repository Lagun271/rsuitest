# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
# One-time setup, fully self-contained: downloads uv into .uv\, a Python into .python\ (version from .python-version),
# creates .venv\ and installs the dependencies in pyproject.toml (rsuitest and through it pywinauto, pillow, psutil).
# Re-running is harmless. Needs internet (astral.sh, github.com, pypi.org); git only for a git+https dependency.
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
$uv = "$PSScriptRoot\.uv\uv.exe"
if (-not (Test-Path $uv)) {
    Write-Host "Downloading uv into $PSScriptRoot\.uv ..."
    $env:UV_UNMANAGED_INSTALL = "$PSScriptRoot\.uv"       # binaries only, no receipt, no PATH change
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    if (-not (Test-Path $uv)) { throw "uv.exe not found after install" }
}
Push-Location $PSScriptRoot
try {
    & $uv python install            # version from .python-version, into .python\
    & $uv sync                      # creates .venv\ and installs the dependencies
    & $uv run python -c "import sys, pywinauto, rsuitest; print('OK: Python', sys.version.split()[0], 'pywinauto', pywinauto.__version__, 'rsuitest', rsuitest.__version__, 'at', sys.prefix)"
} finally { Pop-Location }
