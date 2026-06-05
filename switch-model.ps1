<#
  switch-model.ps1 - flip Porter between named local model profiles.

  This is the reversible switch layer above switch-llm.ps1. It edits only the llm
  profile fields in config.yaml: provider, base_url, model, num_ctx, embedding_model,
  and the informational capability context values. No downloaded model is deleted.

  LM Studio profiles use a stable served identifier (llm.model). porter.local.ps1
  maps that identifier to the actual downloaded LM Studio model key and GPU policy.

  Usage:
    .\switch-model.ps1 porter12b       # default: Google Gemma 4 12B @ 65K
    .\switch-model.ps1 12b             # short alias for porter12b
    .\switch-model.ps1 porter12b-128k  # explicit long-context 12B profile
    .\switch-model.ps1 porter12b-max   # explicit max-context 12B profile (262144)
    .\switch-model.ps1 gemma4          # legacy/easy switch: Google Gemma 4 E4B @ 65K
    .\switch-model.ps1 e4b             # short alias for gemma4
    .\switch-model.ps1 gemma4-32k      # legacy fast E4B @ 32K
    .\switch-model.ps1 gemma4-128k     # legacy max E4B @ 128K
    .\switch-model.ps1 ollama-gemma4   # route back to Ollama Gemma E4B @ 65K
    .\switch-model.ps1                 # show the active profile

  After switching, run: porter
#>
param(
    [ValidateSet(
        'porter12b',
        '12b',
        'porter12b-65k',
        '12b-65k',
        'porter12b-128k',
        '12b-128k',
        'porter12b-max',
        '12b-max',
        'gemma4-32k',
        'e4b-32k',
        'gemma4',
        'e4b',
        'gemma4-65k',
        'e4b-65k',
        'gemma4-128k',
        'e4b-128k',
        'ollama-gemma4',
        'ollama',
        'status'
    )]
    [string]$Target = 'status'
)

$ErrorActionPreference = 'Stop'
$configPath = Join-Path $PSScriptRoot 'config.yaml'

# Context is kept equal in LM Studio load args and in Porter's prompt budget.
# 12B is the current main profile. On this RTX 4060 Laptop 8 GB, the live
# LM Studio GUI load measured about 7.8 GiB VRAM at 65K with partial GPU offload.
# 128K/max are intentionally explicit because they need more RAM/offload and can
# be slower or fail under LM Studio guardrails.
$profiles = @{
    'porter12b'      = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-12B';      num_ctx = 65536;  embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 262144; practical_context = 65536 }
    'porter12b-65k'  = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-12B';      num_ctx = 65536;  embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 262144; practical_context = 65536 }
    'porter12b-128k' = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-12B';      num_ctx = 131072; embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 262144; practical_context = 131072 }
    'porter12b-max'  = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-12B';      num_ctx = 262144; embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 262144; practical_context = 262144 }
    'gemma4-32k'     = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-LMStudio'; num_ctx = 32768;  embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 131072; practical_context = 32768 }
    'gemma4'         = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-LMStudio'; num_ctx = 65536;  embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 131072; practical_context = 65536 }
    'gemma4-65k'     = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-LMStudio'; num_ctx = 65536;  embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 131072; practical_context = 65536 }
    'gemma4-128k'    = @{ provider = 'lmstudio'; base_url = 'http://localhost:1234'; model = 'Porter-LMStudio'; num_ctx = 131072; embedding_model = 'text-embedding-nomic-embed-text-v1.5'; context_window = 131072; practical_context = 131072 }
    'ollama-gemma4'  = @{ provider = 'ollama';   base_url = 'http://localhost:11434'; model = 'gemma4:e4b';     num_ctx = 65536;  embedding_model = 'nomic-embed-text'; context_window = 131072; practical_context = 65536 }
}

$aliases = @{
    '12b'       = 'porter12b'
    '12b-65k'   = 'porter12b-65k'
    '12b-128k'  = 'porter12b-128k'
    '12b-max'   = 'porter12b-max'
    'e4b'       = 'gemma4'
    'e4b-65k'   = 'gemma4-65k'
    'e4b-32k'   = 'gemma4-32k'
    'e4b-128k'  = 'gemma4-128k'
    'ollama'    = 'ollama-gemma4'
}
if ($aliases.ContainsKey($Target)) { $Target = $aliases[$Target] }

function Get-LlmBlock([string]$raw) {
    $m = [regex]::Match($raw, '(?ms)^llm:.*?(?=^\S)')
    if ($m.Success) { return $m.Value }
    return $raw
}

function Get-LlmField([string]$raw, [string]$key) {
    $block = Get-LlmBlock $raw
    $fm = [regex]::Match($block, '(?m)^\s*' + [regex]::Escape($key) + ':\s*"?([^"#\r\n]+)"?')
    if ($fm.Success) { return $fm.Groups[1].Value.Trim() }
    return '(unset)'
}

function Set-QuotedField([string]$block, [string]$key, [string]$value) {
    return [regex]::Replace($block, '(?m)^(\s*' + [regex]::Escape($key) + ':\s*)"[^"]*"', '${1}"' + $value + '"')
}

function Set-IntField([string]$block, [string]$key, [int]$value) {
    return [regex]::Replace($block, '(?m)^(\s*' + [regex]::Escape($key) + ':\s*)\d+', '${1}' + $value)
}

$bytes = [System.IO.File]::ReadAllBytes($configPath)
$hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
$raw = [System.IO.File]::ReadAllText($configPath)

if ($Target -eq 'status') {
    $activeProvider = Get-LlmField $raw 'provider'
    $activeModel = Get-LlmField $raw 'model'
    $activeCtx = Get-LlmField $raw 'num_ctx'
    $activeName = ($profiles.GetEnumerator() | Where-Object {
            $_.Value.provider -eq $activeProvider -and
            $_.Value.model -eq $activeModel -and
            [string]$_.Value.num_ctx -eq [string]$activeCtx
        } | Select-Object -First 1).Key

    Write-Host "Active model profile : $(if ($activeName) { $activeName } else { '(custom)' })" -ForegroundColor Cyan
    Write-Host "  provider           : $activeProvider"
    Write-Host "  base_url           : $(Get-LlmField $raw 'base_url')"
    Write-Host "  model (identifier) : $activeModel"
    Write-Host "  num_ctx            : $activeCtx"
    Write-Host "  embedding_model    : $(Get-LlmField $raw 'embedding_model')"
    Write-Host ""
    Write-Host "Switch with:  .\switch-model.ps1 12b | 12b-128k | 12b-max | e4b | ollama" -ForegroundColor DarkGray
    return
}

$preset = $profiles[$Target]
$fromProvider = Get-LlmField $raw 'provider'
$fromModel = Get-LlmField $raw 'model'
$fromCtx = Get-LlmField $raw 'num_ctx'

$blockMatch = [regex]::Match($raw, '(?ms)^llm:.*?(?=^\S)')
if (-not $blockMatch.Success) { throw "Could not locate the 'llm:' block in $configPath" }

$block = $blockMatch.Value
foreach ($key in 'provider', 'base_url', 'model', 'embedding_model') {
    $block = Set-QuotedField $block $key ([string]$preset[$key])
}
$block = Set-IntField $block 'num_ctx' ([int]$preset.num_ctx)
$block = Set-IntField $block 'context_window' ([int]$preset.context_window)
$block = Set-IntField $block 'practical_context' ([int]$preset.practical_context)
$raw = $raw.Substring(0, $blockMatch.Index) + $block + $raw.Substring($blockMatch.Index + $blockMatch.Length)

$enc = New-Object System.Text.UTF8Encoding($hasBom)
[System.IO.File]::WriteAllText($configPath, $raw, $enc)

Write-Host "Switched model profile: $fromProvider/$fromModel@$fromCtx -> $($preset.provider)/$($preset.model)@$($preset.num_ctx) ($Target)" -ForegroundColor Green
Write-Host "  provider           : $($preset.provider)"
Write-Host "  base_url           : $($preset.base_url)"
Write-Host "  model (identifier) : $($preset.model)"
Write-Host "  num_ctx            : $($preset.num_ctx)"
Write-Host "  embedding_model    : $($preset.embedding_model)"
Write-Host ""
Write-Host "Now 'porter' loads this profile. LM Studio identifiers are mapped in porter.local.ps1." -ForegroundColor DarkGray
