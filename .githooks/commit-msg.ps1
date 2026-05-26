Param([string]$file)
# Prefer project's virtualenv Python if present, then $env:PYTHON, then system `python`
$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
	$python = $venvPython
} elseif ($env:PYTHON) {
	$python = $env:PYTHON
} else {
	$python = "python"
}

& "$python" (Join-Path $PSScriptRoot 'check_commit_msg.py') $file
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
