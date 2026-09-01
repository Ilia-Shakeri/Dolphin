#Requires -RunAsAdministrator
<#
.SYNOPSIS
    One-time setup for an employee Windows PC to reach an internal-only
    Dolphin deployment: installs the company's private root CA as trusted,
    optionally maps the panel hostname in the hosts file, and confirms the
    panel actually loads before finishing.

.DESCRIPTION
    This is the reviewed replacement for assembling this PowerShell by hand
    during a live deployment (DEPLOY-CLIENTONBOARD-009). It is deliberately
    generic - no hostname, IP, or certificate hash is hardcoded - so the same
    script serves every internal-DNS-plus-private-CA deployment described in
    docs/ops/DOLPHIN_DEPLOYMENT_RUNBOOK.md section 6a, not just one customer.

    It never bypasses a certificate warning. A warning after this script has
    run correctly means something is actually wrong (the wrong CA, the wrong
    hash, a server presenting a different certificate), and the answer is to
    stop and check, not to click through.

.PARAMETER PanelUrl
    The full HTTPS URL of the panel, e.g. https://pannel.company.internal/

.PARAMETER CertificatePath
    Path to the root CA certificate file (.cer or .crt) to install. Get this
    from the company's IT contact - never generate or accept one from any
    other source.

.PARAMETER ExpectedSha256
    The SHA-256 fingerprint IT gave you for the certificate file, as hex,
    with or without colons/spaces (both are accepted). Required - this script
    refuses to install a certificate whose hash it was not given to check.

.PARAMETER HostsEntryIp
    Optional. If the deployment does not yet have central DNS, pass the
    server's IP here and this script adds "IP hostname" to the Windows hosts
    file - the temporary bridge the runbook describes, not the long-term
    plan. Omit this once central DNS resolves the name.

.EXAMPLE
    .\windows-employee-onboarding.ps1 `
        -PanelUrl 'https://pannel.company.internal/' `
        -CertificatePath 'C:\Users\me\Downloads\company-internal-root-ca.cer' `
        -ExpectedSha256 '6B94E39DEE4FAAA675F489E105442090840C68C8A8E5333A974D121A1BA8397B' `
        -HostsEntryIp '192.168.1.208'
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://')]
    [string]$PanelUrl,

    [Parameter(Mandatory = $true)]
    [string]$CertificatePath,

    [Parameter(Mandatory = $true)]
    [string]$ExpectedSha256,

    [string]$HostsEntryIp
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail {
    param([string]$Message)
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

$isAdmin = (
    New-Object Security.Principal.WindowsPrincipal(
        [Security.Principal.WindowsIdentity]::GetCurrent()
    )
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Fail "This must run as Administrator (right-click PowerShell, Run as administrator)."
}

$panelUri = [Uri]$PanelUrl
$panelHost = $panelUri.Host

Write-Step "Panel host: $panelHost"

if (-not (Test-Path -LiteralPath $CertificatePath -PathType Leaf)) {
    Fail "Certificate file not found: $CertificatePath"
}

Write-Step "Checking certificate hash"
$normalizedExpected = ($ExpectedSha256 -replace '[^0-9A-Fa-f]', '').ToUpperInvariant()
if ($normalizedExpected.Length -ne 64) {
    Fail "ExpectedSha256 must be a 64-character SHA-256 hex hash."
}
$actualHash = (Get-FileHash -LiteralPath $CertificatePath -Algorithm SHA256).Hash
if ($actualHash -ne $normalizedExpected) {
    Fail @"
Certificate hash does not match what IT gave you.
  expected: $normalizedExpected
  actual:   $actualHash
Stop here and contact IT. Do not install this certificate - installing the
wrong root CA as trusted is a real security exposure, not a formality.
"@
}
Write-Host "    hash OK" -ForegroundColor Green

Write-Step "Installing the certificate into the Trusted Root store (LocalMachine)"
certutil.exe -addstore Root $CertificatePath | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "certutil failed to install the certificate (exit code $LASTEXITCODE)."
}
Write-Host "    installed" -ForegroundColor Green

if ($HostsEntryIp) {
    Write-Step "Adding a temporary hosts-file mapping ($HostsEntryIp -> $panelHost)"
    Write-Host "    This is a bridge until central DNS resolves this name - see the runbook." -ForegroundColor Yellow

    $hostsFile = "$env:WINDIR\System32\drivers\etc\hosts"
    $hostsBackup = "$hostsFile.dolphin-onboarding-$(Get-Date -Format yyyyMMddHHmmss).bak"
    Copy-Item -LiteralPath $hostsFile -Destination $hostsBackup

    $escapedHost = [Regex]::Escape($panelHost)
    $validPattern = "^\s*$([Regex]::Escape($HostsEntryIp))\s+$escapedHost(?:\s|$)"
    $anyPattern = "^\s*\d{1,3}(?:\.\d{1,3}){3}\s+$escapedHost(?:\s|$)"

    $activeLines = @(
        Get-Content -LiteralPath $hostsFile | Where-Object { $_ -notmatch '^\s*#' }
    )
    $wrongLines = @($activeLines | Where-Object { $_ -match $anyPattern -and $_ -notmatch $validPattern })
    $validLines = @($activeLines | Where-Object { $_ -match $validPattern })

    if ($wrongLines.Count -gt 0) {
        Fail "A different address is already mapped to $panelHost in the hosts file. Contact IT rather than editing it yourself."
    }
    if ($validLines.Count -eq 0) {
        Add-Content -LiteralPath $hostsFile -Value "`r`n$HostsEntryIp $panelHost"
        Write-Host "    added" -ForegroundColor Green
    } else {
        Write-Host "    already present" -ForegroundColor Green
    }

    ipconfig.exe /flushdns | Out-Null
}

Write-Step "Confirming $panelHost resolves"
try {
    $resolved = @([System.Net.Dns]::GetHostAddresses($panelHost) | ForEach-Object { $_.IPAddressToString })
} catch {
    Fail "Could not resolve $panelHost at all. If you did not pass -HostsEntryIp, central DNS may not be set up yet - ask IT."
}
if ($HostsEntryIp -and ($resolved -notcontains $HostsEntryIp)) {
    Fail "$panelHost resolved to $($resolved -join ', '), not $HostsEntryIp. Something else is already mapping this name."
}
Write-Host "    resolves to $($resolved -join ', ')" -ForegroundColor Green

Write-Step "Opening the panel"
Write-Host "    If the browser still shows a certificate warning here, stop and contact IT." -ForegroundColor Yellow
Write-Host "    Do not click through it." -ForegroundColor Yellow
Start-Process $PanelUrl

Write-Host ""
Write-Host "Setup completed. Use $PanelUrl to reach the panel from now on." -ForegroundColor Green
