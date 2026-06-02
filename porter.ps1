<#
.SYNOPSIS
    Launch "Porter" - your local Strategy Agent (fully local; LLM backend per config.yaml,
    switchable between Ollama and LM Studio via switch-llm.ps1).

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
    # Optional machine-specific pre-launch hook (gitignored, not in the repo).
    # Use it for environment setup that should run before the agent starts — e.g.
    # auto-starting the LM Studio server + loading the model so plain 'porter' just
    # works. Absent on a fresh clone (Ollama path needs nothing extra).
    $localHook = Join-Path $root "porter.local.ps1"
    if (Test-Path $localHook) { & $localHook }

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
