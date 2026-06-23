# switch-profile.ps1 — switch Porter's active dimension profile (Block B).
#
# One codebase, per-department behaviour. Mirrors switch-model.ps1 but for dimensions:
#   .\switch-profile.ps1              # show the active profile + all choices
#   .\switch-profile.ps1 analyst      # Analyst dimension (read & evaluate docs; e.g. CV screening)
#   .\switch-profile.ps1 builder      # Builder dimension (create artifacts; e.g. mgmt reporting)
#   .\switch-profile.ps1 research     # Research / Strategy dimension
#   .\switch-profile.ps1 all          # the all-rounder (every dimension) — the default
#
# Delegates to `python main.py profile <name>` so validation lives in one place
# (core/profile.py). The choice is stored in ./.porter_profile (gitignored, machine-local),
# never in config.yaml — so it never collides with in-progress config edits.

param([string]$Profile = "")

$ErrorActionPreference = "Stop"
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$main = Join-Path $PSScriptRoot "main.py"

if (-not (Test-Path $py)) { $py = "python" }  # fall back to PATH python if no venv

if ($Profile -eq "") {
    & $py $main profile
} else {
    & $py $main profile $Profile
}
