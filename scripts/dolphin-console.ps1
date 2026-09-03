<#
.SYNOPSIS
    Launches the local deployment console as a desktop window.

.DESCRIPTION
    A double-click-friendly shortcut for platform owners around
    `python scripts/manifest_builder.py --desktop` — the "desktop mini-app"
    idea in DOLPHIN_FEATURE_MAP_AND_ROADMAP.md section 6. Same tool, same
    127.0.0.1-only server, same security boundary as the plain browser mode;
    this only changes what opens to show it.

    Needs pywebview on this machine (`pip install -r scripts/requirements-
    console.txt`). If it is missing, manifest_builder.py itself explains
    that and exits - this script does not duplicate that check, so the one
    place that decides "is pywebview installed" never has two answers.

.PARAMETER Port
    Local port for the console's own HTTP server. Default 8799, same as
    manifest_builder.py's own default.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\dolphin-console.ps1
#>

param(
    [int]$Port = 8799
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent $PSScriptRoot

Push-Location $repositoryRoot
try {
    python scripts/manifest_builder.py --desktop --port $Port
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
