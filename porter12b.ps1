<#
.SYNOPSIS
    One-command cold-start launcher for Porter on Google Gemma 4 12B @ 65K context.

.DESCRIPTION
    Sets the active model profile to Porter-12B / 65536 context and then delegates to
    porter.ps1. The normal Porter pre-launch hook still does the real work: starts
    SearXNG when needed, starts LM Studio, loads the model, verifies a chat request,
    and preloads the embedding model.

    Usage:
        porter12b
        porter12b ask "Was macht Neura Robotics?"
        porter12b analyze "..." --effort ultra

    Long-context variants are intentionally explicit:
        .\switch-model.ps1 porter12b-128k
        .\switch-model.ps1 porter12b-max
#>

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

& (Join-Path $root "switch-model.ps1") porter12b | Out-Host
& (Join-Path $root "porter.ps1") @args
