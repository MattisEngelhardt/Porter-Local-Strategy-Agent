<#
.SYNOPSIS
    Launch "Porter" - your local Strategy Agent (fully local; gemma4:e4b via Ollama).

.DESCRIPTION
    Starts the interactive agent REPL from the project root, using the project's
    virtual-environment Python if present (otherwise the system 'python'). Any
    arguments are passed straight through to main.py, so this single launcher also
    covers the one-shot commands:

        porter                                  # interactive REPL (chat with Porter)
        porter ask "Was macht Neura Robotics?"  # single question
        porter analyze "..." --effort ultra     # full pipeline, non-interactive
        porter prepare report.pdf --format deck # consolidate documents

    Add a 'porter' function to your PowerShell $PROFILE (see README) to run it from
    anywhere by just typing: porter
#>

$ErrorActionPreference = "Stop"

# Resolve the project root from this script's own location (robust to the caller's cwd).
$root = $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

Push-Location $root
try {
    if (Test-Path $venvPython) {
        & $venvPython "main.py" @args
    } else {
        Write-Host "[porter] .venv not found at $venvPython - using system 'python'." -ForegroundColor Yellow
        Write-Host "[porter] Create it once:  python -m venv .venv ;  .\.venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
        & python "main.py" @args
    }
} finally {
    Pop-Location
}
