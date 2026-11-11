# Copyright (c) 2026 Lagun 271 AB. MIT licence, see LICENSE.md at https://github.com/Lagun271/rsuitest.
# Run a test script from this folder with the self-contained Python (setup.ps1 runs first if there is no .venv):
#   .\run.ps1 <test script>                 runs <test script>.py from this folder
#   .\run.ps1 <test script> -- <arguments>  arguments after -- go to the script
#   .\run.ps1 status | close | dump_tree | pim   no such .py here: runs the rsuitest module (python -m rsuitest.<name>)
param([Parameter(Mandatory)][string]$Test, [Parameter(ValueFromRemainingArguments)][string[]]$Rest)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1"
if (-not (Test-Path "$PSScriptRoot\.venv")) { & "$PSScriptRoot\setup.ps1" }
$Rest = @($Rest | Where-Object { $_ -and $_ -ne '--' })
[string[]]$target = if (Test-Path "$PSScriptRoot\$Test.py") { @("$PSScriptRoot\$Test.py") } else { @('-m', "rsuitest.$Test") }
Push-Location $PSScriptRoot
try { & "$PSScriptRoot\.uv\uv.exe" run python @target @Rest; exit $LASTEXITCODE } finally { Pop-Location }
