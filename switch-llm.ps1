<#
  switch-llm.ps1 — flip the Strategy Agent between local LLM backends.

  A reversible "switch button": it edits ONLY the four llm.* fields in config.yaml
  (provider, base_url, model, embedding_model). Nothing else is touched, nothing is
  deleted, and switching back is one command. Both backends stay installed.

  Usage:
    .\switch-llm.ps1 lmstudio   # route the agent at LM Studio (:1234)
    .\switch-llm.ps1 ollama     # route the agent back at Ollama (:11434)
    .\switch-llm.ps1            # show the active backend (no changes)

  When switching to lmstudio the chat model id is auto-detected from the running
  LM Studio server (/v1/models), so you never have to hand-edit it.
#>
param(
    [ValidateSet('ollama', 'lmstudio', 'status')]
    [string]$Target = 'status'
)

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'config.yaml'

# --- the only fields that differ between backends ---
$presets = @{
    ollama   = @{
        provider        = 'ollama'
        base_url        = 'http://localhost:11434'
        model           = 'gemma4:e4b'
        embedding_model = 'nomic-embed-text'
    }
    lmstudio = @{
        provider        = 'lmstudio'
        base_url        = 'http://localhost:1234'
        model           = 'google/gemma-4-e4b'                  # auto-detected if server is up
        embedding_model = 'text-embedding-nomic-embed-text-v1.5'
    }
}

function Get-LlmField([string]$raw, [string]$key) {
    $m = [regex]::Match($raw, '(?ms)^llm:.*?(?=^\S)')
    $block = if ($m.Success) { $m.Value } else { $raw }
    $fm = [regex]::Match($block, '(?m)^\s*' + [regex]::Escape($key) + ':\s*"([^"]*)"')
    if ($fm.Success) { return $fm.Groups[1].Value }
    return '(unset)'
}

# Read raw text + remember BOM so we write the file back byte-identical in style.
$bytes = [System.IO.File]::ReadAllBytes($configPath)
$hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
$raw = [System.IO.File]::ReadAllText($configPath)

# --- status: just report, change nothing ---
if ($Target -eq 'status') {
    Write-Host "Active LLM backend : $(Get-LlmField $raw 'provider')" -ForegroundColor Cyan
    Write-Host "  base_url         : $(Get-LlmField $raw 'base_url')"
    Write-Host "  model            : $(Get-LlmField $raw 'model')"
    Write-Host "  embedding_model  : $(Get-LlmField $raw 'embedding_model')"
    return
}

$from = Get-LlmField $raw 'provider'
$preset = $presets[$Target].Clone()

# When targeting LM Studio, auto-detect the loaded chat model from the server so the
# id is always correct (falls back to the preset default if the server is unreachable).
if ($Target -eq 'lmstudio') {
    try {
        $models = (Invoke-RestMethod -Uri 'http://localhost:1234/v1/models' -TimeoutSec 4).data
        $chat = $models | Where-Object { $_.id -notmatch 'embed' } | Select-Object -First 1
        if ($chat) { $preset.model = $chat.id }
        $emb = $models | Where-Object { $_.id -match 'embed' } | Select-Object -First 1
        if ($emb) { $preset.embedding_model = $emb.id }
    }
    catch {
        Write-Host "note: LM Studio server not reachable on :1234 - using preset model id '$($preset.model)'." -ForegroundColor Yellow
        Write-Host "      start it first with the lms CLI:  lms server start" -ForegroundColor Yellow
    }
}

# --- swap only the four fields, only inside the llm: block ---
$blockMatch = [regex]::Match($raw, '(?ms)^llm:.*?(?=^\S)')
if (-not $blockMatch.Success) { throw "Could not locate the 'llm:' block in $configPath" }
$block = $blockMatch.Value
foreach ($key in 'provider', 'base_url', 'model', 'embedding_model') {
    # anchored so 'model' never matches 'embedding_model'; trailing comments are preserved
    $block = [regex]::Replace($block, '(?m)^(\s*' + $key + ':\s*)"[^"]*"', '${1}"' + $preset[$key] + '"')
}
$raw = $raw.Substring(0, $blockMatch.Index) + $block + $raw.Substring($blockMatch.Index + $blockMatch.Length)

$enc = New-Object System.Text.UTF8Encoding($hasBom)
[System.IO.File]::WriteAllText($configPath, $raw, $enc)

Write-Host "Switched LLM backend: $from -> $Target" -ForegroundColor Green
Write-Host "  base_url         : $($preset.base_url)"
Write-Host "  model            : $($preset.model)"
Write-Host "  embedding_model  : $($preset.embedding_model)"
Write-Host ""
Write-Host "Now 'porter' uses this backend. Switch back any time with: .\switch-llm.ps1 $from" -ForegroundColor DarkGray
