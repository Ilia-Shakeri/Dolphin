# Security scan evidence runbook

Status: repository procedure complete; registry, advisory-service, container-engine, public-network, and reviewer proof remains external.

This procedure creates evidence for one immutable source commit, all three exact runtime images, and the exact Python build-base digest. It covers source-secret detection, the locked Python dependency set, per-image SBOMs and vulnerabilities for the application, PostgreSQL, and Nginx, the recorded Python base input, and the real public TLS endpoint. A completed command is not a passing review. The security owner must review every report and record the result against the same release reference.

## Trust and evidence boundary

- Run this from a clean checkout at the approved release commit on an isolated evidence host. Do not run the image scanners through a production container engine.
- Use only scanner images whose exact released tool version was reviewed and resolved to an immutable registry digest. `latest`, branch, tag-only, or locally named references are forbidden.
- Use the exact deployable `KARIZ_APP_IMAGE`, `KARIZ_POSTGRES_IMAGE`, and `KARIZ_NGINX_IMAGE` `repository@sha256:digest` references. Record the exact `PYTHON_BASE_IMAGE` digest from the approved build record. Do not scan a local build tag as release proof.
- Pre-create one approved, encrypted, restricted evidence root outside the repository, checkout parent, temporary directories, and shared or synchronized user folders. The commands create one new child and never overwrite a prior run.
- Registry authentication, when needed, must already exist in the host's approved credential helper. Never put a registry password or token in a command, environment variable, report, or transcript.
- The source report is a deliberately reduced report. It stores rule, repository path, line range, and commit only. It never stores the matched line or suspected value.
- SBOM, package, file-path, certificate, and vulnerability data can still be sensitive. Keep all output restricted even when no finding exists.
- The SBOM scanner receives the local container-engine socket. That socket is equivalent to control of that isolated engine. Approve the scanner image first, keep production workloads off that engine, and remove host access after the run.

Before the run, record the evidence owner, security reviewer, retention class and end condition, approved external TLS client label, approved release commit, three exact runtime image references, exact Python build-base reference, approved source-to-image build record, and all five exact scanner image references in the release record. Do not record secrets.

## Exact inputs and protected run directory

Open a new PowerShell session at the repository root. Enter only non-secret identifiers at the prompts.

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path -LiteralPath '.').Path
$approvedReleaseCommit = (Read-Host 'Approved 40-hex release commit').Trim().ToLowerInvariant()
$appImage = (Read-Host 'Approved application image repository@sha256:digest').Trim()
$postgresImage = (Read-Host 'Approved PostgreSQL image repository@sha256:digest').Trim()
$nginxImage = (Read-Host 'Approved Nginx image repository@sha256:digest').Trim()
$pythonBaseImage = (Read-Host 'Approved Python build-base repository@sha256:digest').Trim()
$gitleaksImage = (Read-Host 'Approved Gitleaks image repository@sha256:digest').Trim()
$pipAuditImage = (Read-Host 'Approved pip-audit image repository@sha256:digest').Trim()
$syftImage = (Read-Host 'Approved Syft image repository@sha256:digest').Trim()
$grypeImage = (Read-Host 'Approved Grype image repository@sha256:digest').Trim()
$testsslImage = (Read-Host 'Approved testssl.sh image repository@sha256:digest').Trim()
$publicHost = (Read-Host 'Approved lowercase public hostname').Trim()
$externalClientLabel = (Read-Host 'Approved non-secret external TLS client label').Trim()
$evidenceRootInput = (Read-Host 'Approved restricted external evidence root').Trim()

if ($approvedReleaseCommit -notmatch '^[0-9a-f]{40}$') {
    throw 'Release commit must be exactly 40 lowercase hexadecimal characters.'
}

$actualReleaseCommit = (git rev-parse --verify HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $actualReleaseCommit -ne $approvedReleaseCommit) {
    throw 'Checkout does not match the approved release commit.'
}

$sourceState = @(git status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $sourceState.Count -ne 0) {
    throw 'Release checkout must be clean, including untracked files.'
}

$pinnedImagePattern = '^[a-z0-9][a-z0-9._-]*(?::[0-9]+)?(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[a-f0-9]{64}$'
$runtimeImages = [ordered]@{
    application = $appImage
    postgresql = $postgresImage
    nginx = $nginxImage
}
$scannerImages = [ordered]@{
    gitleaks = $gitleaksImage
    pip_audit = $pipAuditImage
    syft = $syftImage
    grype = $grypeImage
    testssl = $testsslImage
}

foreach ($value in @($runtimeImages.Values) + @($pythonBaseImage) + @($scannerImages.Values)) {
    if ($value -notmatch $pinnedImagePattern) {
        throw 'Every runtime, build-base, and scanner image must use one exact repository@sha256 registry digest.'
    }
}

if ($publicHost.Length -gt 253 -or $publicHost -notmatch '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$') {
    throw 'Public host must be one lowercase DNS hostname with no scheme, port, path, or wildcard.'
}
if ([string]::IsNullOrWhiteSpace($externalClientLabel) -or $externalClientLabel.Length -gt 128) {
    throw 'External client label is required and must be at most 128 characters.'
}

$evidenceRoot = (Resolve-Path -LiteralPath $evidenceRootInput).Path
$evidenceRootItem = Get-Item -Force -LiteralPath $evidenceRoot
if (-not $evidenceRootItem.PSIsContainer -or ($evidenceRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Evidence root must be a real directory, not a link or reparse point.'
}

$repoPrefix = $repoRoot.TrimEnd('\') + '\'
$repoParent = (Split-Path -Parent $repoRoot).TrimEnd('\')
$repoParentPrefix = $repoParent + '\'
$evidencePrefix = $evidenceRoot.TrimEnd('\') + '\'
if (
    $evidenceRoot -eq $repoRoot -or
    $evidenceRoot -eq $repoParent -or
    $evidencePrefix.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $evidencePrefix.StartsWith($repoParentPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $repoPrefix.StartsWith($evidencePrefix, [StringComparison]::OrdinalIgnoreCase)
) {
    throw 'Evidence root must be outside the repository and its parent path.'
}

$appDigest = ($appImage -split '@sha256:', 2)[1]
$runStartedUtc = [DateTime]::UtcNow.ToString('o')
$runLeaf = '{0}-{1}-{2}' -f [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'), $approvedReleaseCommit, $appDigest.Substring(0, 16)
$evidenceDir = Join-Path $evidenceRoot $runLeaf
if (Test-Path -LiteralPath $evidenceDir) {
    throw 'Evidence run directory already exists.'
}
New-Item -ItemType Directory -Path $evidenceDir | Out-Null
Set-Content -LiteralPath (Join-Path $evidenceDir 'run-state.txt') -Value 'INCOMPLETE' -Encoding utf8

$requirementsSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $repoRoot 'requirements.txt')).Hash.ToLowerInvariant()
$tlsTarget = "${publicHost}:443"
```

Stop if the evidence owner has not checked the inherited access controls on the new directory. Only the evidence custodian, security reviewer, and named release owner may read it; only the evidence custodian may modify it.

## Pull and prove immutable images

Pull each exact reference for the production target. The registry validates the requested manifest digest. The later local check rejects any runtime, build-base, or scanner reference that is not present under that digest.

```powershell
$allImages = @($runtimeImages.Values) + @($pythonBaseImage) + @($scannerImages.Values)
foreach ($image in $allImages) {
    docker pull --platform linux/amd64 $image
    if ($LASTEXITCODE -ne 0) {
        throw 'Exact image pull failed.'
    }
}

function Assert-LocalDigest([string]$image) {
    $digest = ($image -split '@', 2)[1]
    $repoDigests = @(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' $image)
    if ($LASTEXITCODE -ne 0 -or -not ($repoDigests | Where-Object { $_.Trim().EndsWith("@$digest", [StringComparison]::OrdinalIgnoreCase) })) {
        throw 'Local image does not expose the approved registry digest.'
    }
}

foreach ($image in $allImages) {
    Assert-LocalDigest $image
}

$imagePlatforms = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $platform = (docker image inspect --format '{{.Os}}/{{.Architecture}}' $entry.Value).Trim()
    if ($LASTEXITCODE -ne 0 -or $platform -ne 'linux/amd64') {
        throw 'A runtime image is not the approved linux/amd64 target.'
    }
    $imagePlatforms[$entry.Key] = $platform
}
$pythonBasePlatform = (docker image inspect --format '{{.Os}}/{{.Architecture}}' $pythonBaseImage).Trim()
if ($LASTEXITCODE -ne 0 -or $pythonBasePlatform -ne 'linux/amd64') {
    throw 'Python build-base image is not the approved linux/amd64 target.'
}
```

Record runtime tool version output from the already digest-pinned scanner images. The approved pip-audit scanner image must contain its named tool and Python entry point; do not install a scanner during this release run.

```powershell
$gitleaksVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $gitleaksImage --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($gitleaksVersion)) { throw 'Gitleaks version probe failed.' }

$pipAuditVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --entrypoint python $pipAuditImage -m pip_audit --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pipAuditVersion)) { throw 'pip-audit version probe failed.' }

$syftVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $syftImage version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($syftVersion)) { throw 'Syft version probe failed.' }

$grypeVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $grypeImage version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($grypeVersion)) { throw 'Grype version probe failed.' }

$testsslVersion = @(
    docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges $testsslImage --version
) -join "`n"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($testsslVersion)) { throw 'testssl.sh version probe failed.' }

$toolVersions = [ordered]@{
    gitleaks = $gitleaksVersion
    pip_audit = $pipAuditVersion
    syft = $syftVersion
    grype = $grypeVersion
    testssl = $testsslVersion
}
$toolVersions | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $evidenceDir 'tool-versions.json') -Encoding utf8
```

## Source-secret scan

The clean commit is the source-artifact binding. The scan covers reachable Git history, including the approved commit. Do not add a release-time baseline or allowlist. Any exception must already be a reviewed source-controlled scanner rule.

Create a report template that cannot emit the matching line or value:

```powershell
$safeGitleaksTemplate = @'
[
{{- range $index, $finding := . }}{{ if $index }},{{ end }}
{"rule_id":{{ quote .RuleID }},"file":{{ quote .File }},"start_line":{{ .StartLine }},"end_line":{{ .EndLine }},"commit":{{ quote .Commit }}}
{{- end }}
]
'@
$gitleaksTemplatePath = Join-Path $evidenceDir 'gitleaks-safe-report.tmpl'
Set-Content -LiteralPath $gitleaksTemplatePath -Value $safeGitleaksTemplate -Encoding ascii

docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=64m `
    --mount "type=bind,source=$repoRoot,target=/src,readonly" `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    $gitleaksImage git /src `
    --no-banner --no-color --redact=100 `
    --report-format template `
    --report-template /evidence/gitleaks-safe-report.tmpl `
    --report-path /evidence/source-secrets.redacted.json
$gitleaksExit = $LASTEXITCODE

if ($gitleaksExit -notin @(0, 1)) { throw 'Gitleaks execution failed.' }
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'source-secrets.redacted.json') | ConvertFrom-Json
```

Exit `0` means no finding under this scanner version and rule set. Exit `1` is a no-go finding until the security owner investigates. Never copy the suspected value into a ticket, message, exception list, or release record. Preserve only the reduced report and refer to its file and line under restricted access.

## Locked Python dependency scan

This scan binds to the SHA-256 of the exact `requirements.txt` in the approved commit. `--require-hashes` and `--disable-pip` prevent dependency resolution or package installation. The advisory service is live external state, so its name and the run time are part of the evidence; a later release decision may require a fresh run.

```powershell
$pipAuditCache = Join-Path $evidenceDir 'pip-audit-cache'
New-Item -ItemType Directory -Path $pipAuditCache | Out-Null

docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$repoRoot,target=/src,readonly" `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    --entrypoint python `
    $pipAuditImage -m pip_audit `
    --require-hashes --disable-pip --strict `
    --vulnerability-service pypi `
    --progress-spinner off --desc off --aliases on `
    --cache-dir /evidence/pip-audit-cache `
    --format json --output /evidence/python-dependencies.json `
    --requirement /src/requirements.txt
$pipAuditExit = $LASTEXITCODE

if ($pipAuditExit -notin @(0, 1)) { throw 'pip-audit execution failed.' }
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'python-dependencies.json') | ConvertFrom-Json
```

Exit `0` means no known vulnerability was returned at that time. Exit `1` is no-go pending report review; it can mean a finding or a scan failure, so the report and command state must both be checked. Do not suppress a vulnerability ID in this command. A risk acceptance belongs in the separately approved release record.

## Exact runtime-image SBOMs

The local digest proof above binds each Docker source to its exact runtime manifest. Syft scans each squashed deployable filesystem, not deleted content from older layers. It writes a CycloneDX release SBOM and a native report for each runtime-image vulnerability scan. The application filesystem includes its Python base layers; the separately recorded base digest must still match the approved source-to-image build record.

```powershell
$syftExitCodes = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $artifactName = $entry.Key
    $cycloneContainerPath = "/evidence/${artifactName}-sbom.cdx.json"
    $syftContainerPath = "/evidence/${artifactName}-sbom.syft.json"
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=128m `
        --volume /var/run/docker.sock:/var/run/docker.sock `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        $syftImage "docker:$($entry.Value)" --scope squashed `
        --output "cyclonedx-json=$cycloneContainerPath" `
        --output "syft-json=$syftContainerPath"
    $syftExitCodes[$artifactName] = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Runtime-image SBOM generation failed.' }
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-sbom.cdx.json") | ConvertFrom-Json
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-sbom.syft.json") | ConvertFrom-Json
}
```

An SBOM is inventory evidence, not vulnerability or license approval. The reviewer must confirm that each report identifies the expected exact image source and contains the expected operating-system and application package families before accepting it.

## Exact runtime-image vulnerability scans

Update the Grype database into this run directory, capture its schema, build time, checksum, and status, then disable updates for the actual scans. Each scan consumes the SBOM made from one exact runtime image. It reports fixed and unfixed findings; do not use `--only-fixed` and do not provide ignore or VEX input here.

```powershell
$grypeDbDir = Join-Path $evidenceDir 'grype-db'
New-Item -ItemType Directory -Path $grypeDbDir | Out-Null

docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
    --env GRYPE_CHECK_FOR_APP_UPDATE=false `
    $grypeImage db update
if ($LASTEXITCODE -ne 0) { throw 'Grype database update failed.' }

$grypeDbStatus = @(
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=64m `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
        --env GRYPE_DB_AUTO_UPDATE=false `
        --env GRYPE_CHECK_FOR_APP_UPDATE=false `
        $grypeImage db status
) -join "`n"
if ($LASTEXITCODE -ne 0 -or $grypeDbStatus -notmatch '(?im)^Status:\s+valid\s*$') {
    throw 'Grype database is not valid.'
}
Set-Content -LiteralPath (Join-Path $evidenceDir 'grype-db-status.txt') -Value $grypeDbStatus -Encoding utf8

$grypeExitCodes = [ordered]@{}
foreach ($entry in $runtimeImages.GetEnumerator()) {
    $artifactName = $entry.Key
    $sbomContainerPath = "/evidence/${artifactName}-sbom.syft.json"
    $vulnerabilityContainerPath = "/evidence/${artifactName}-vulnerabilities.json"
    docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges `
        --tmpfs /tmp:rw,noexec,nosuid,size=128m `
        --mount "type=bind,source=$evidenceDir,target=/evidence" `
        --env GRYPE_DB_CACHE_DIR=/evidence/grype-db `
        --env GRYPE_DB_AUTO_UPDATE=false `
        --env GRYPE_CHECK_FOR_APP_UPDATE=false `
        $grypeImage "sbom:$sbomContainerPath" `
        --output json --file $vulnerabilityContainerPath `
        --fail-on high
    $grypeExitCodes[$artifactName] = $LASTEXITCODE
    $null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir "${artifactName}-vulnerabilities.json") | ConvertFrom-Json
}
```

For each runtime image, exit `0` means the pinned Grype version did not cross the High threshold. Any nonzero exit is no-go for that image until the reviewer uses that exact pinned version's documented exit contract and the matching parsed report to distinguish a threshold match from execution failure. This avoids treating a changed scanner exit-code contract as a pass. Exit `0` does not waive lower-severity review, false-negative review, or the need to refresh an old vulnerability database.

## Real public TLS scan

Run this section only from the approved external client, outside the target host and internal proxy path. The hostname must resolve through public DNS and the route must terminate at the same edge users reach. The scanner gets no certificate private key, cookie, account, header, or client credential.

```powershell
docker run --rm --read-only --cap-drop ALL --security-opt no-new-privileges `
    --tmpfs /tmp:rw,noexec,nosuid,size=128m `
    --mount "type=bind,source=$evidenceDir,target=/evidence" `
    $testsslImage `
    --quiet --warnings batch --color 0 `
    --jsonfile /evidence/tls-public.json `
    --logfile /evidence/tls-public.log `
    $tlsTarget
$testsslExit = $LASTEXITCODE

if (-not (Test-Path -LiteralPath (Join-Path $evidenceDir 'tls-public.json'))) {
    throw 'TLS scanner did not create JSON evidence.'
}
$null = Get-Content -Raw -LiteralPath (Join-Path $evidenceDir 'tls-public.json') | ConvertFrom-Json
```

A TLS scanner exit code alone is not acceptance. The reviewer must confirm the observed hostname/IP path, certificate name and chain, validity, TLS 1.0/1.1 denial, TLS 1.2/1.3 support, cipher/protocol findings, HSTS through HTTPS, and absence of a release-blocking result. Record the scanner exit code even when the JSON is valid. Browser, renewal, redirect, secure-cookie, CSRF, and port-exposure proof remains required by [TLS.md](TLS.md).

## Bind, seal, and review the evidence

Write factual run metadata from this PowerShell session. `COMPLETE_REVIEW_REQUIRED` means every expected artifact exists and parses; it never means that findings passed review.

```powershell
$runFinishedUtc = [DateTime]::UtcNow.ToString('o')
$metadata = [ordered]@{
    schema_version = 2
    state = 'COMPLETE_REVIEW_REQUIRED'
    release_commit = $approvedReleaseCommit
    requirements_sha256 = $requirementsSha256
    runtime_images = $runtimeImages
    runtime_platforms = $imagePlatforms
    python_build_base_image = $pythonBaseImage
    python_build_base_platform = $pythonBasePlatform
    scanner_images = $scannerImages
    scanner_versions = $toolVersions
    dependency_advisory_service = 'pypi'
    grype_fail_on = 'high'
    public_tls_host = $publicHost
    external_tls_client_label = $externalClientLabel
    run_started_utc = $runStartedUtc
    run_finished_utc = $runFinishedUtc
    exit_codes = [ordered]@{
        gitleaks = $gitleaksExit
        pip_audit = $pipAuditExit
        syft = $syftExitCodes
        grype = $grypeExitCodes
        testssl = $testsslExit
    }
}
$metadata | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidenceDir 'run-metadata.json') -Encoding utf8
Set-Content -LiteralPath (Join-Path $evidenceDir 'run-state.txt') -Value 'COMPLETE_REVIEW_REQUIRED' -Encoding utf8

$reparseEntries = @(Get-ChildItem -Force -Recurse -LiteralPath $evidenceDir | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
if ($reparseEntries.Count -ne 0) {
    throw 'Evidence tree contains a link or reparse point.'
}

$integrityPath = Join-Path $evidenceDir 'integrity.sha256'
$integrityAnchorPath = Join-Path $evidenceDir 'integrity.sha256.anchor'
$evidenceFiles = @(
    Get-ChildItem -Force -Recurse -File -LiteralPath $evidenceDir |
        Where-Object { $_.FullName -notin @($integrityPath, $integrityAnchorPath) } |
        Sort-Object FullName
)
$integrityLines = foreach ($file in $evidenceFiles) {
    $relativePath = $file.FullName.Substring($evidenceDir.Length + 1).Replace('\', '/')
    $fileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    '{0}  {1}' -f $fileHash, $relativePath
}
$integrityLines | Set-Content -LiteralPath $integrityPath -Encoding ascii
$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $integrityPath).Hash.ToLowerInvariant()
Set-Content -LiteralPath $integrityAnchorPath -Value ("$manifestHash  integrity.sha256") -Encoding ascii

Write-Output "Record this out-of-band evidence anchor in the approved release record: sha256:$manifestHash"
```

The evidence custodian must copy only the final manifest SHA-256 to the separately controlled release record or write-once evidence index. The in-directory anchor is convenient but is not an independent trust anchor. Do not modify, rename, append to, or regenerate any file after the manifest is sealed; a rerun gets a new directory and time.

Verify the sealed directory at review, transfer, incident use, and retention expiry. Supply the anchor from the separately controlled release record, not from `integrity.sha256.anchor`:

```powershell
$sealedEvidenceDir = (Resolve-Path -LiteralPath (Read-Host 'Sealed evidence run directory')).Path
$approvedManifestHash = (Read-Host 'Out-of-band approved integrity.sha256 SHA-256').Trim().ToLowerInvariant()
if ($approvedManifestHash -notmatch '^[0-9a-f]{64}$') { throw 'Approved manifest hash is invalid.' }

$sealedPrefix = $sealedEvidenceDir.TrimEnd('\') + '\'
$sealedManifest = Join-Path $sealedEvidenceDir 'integrity.sha256'
$actualManifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sealedManifest).Hash.ToLowerInvariant()
if ($actualManifestHash -ne $approvedManifestHash) { throw 'Evidence manifest hash mismatch.' }

$manifestPaths = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($line in Get-Content -LiteralPath $sealedManifest) {
    if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Malformed integrity manifest row.' }
    $expectedHash = $Matches[1]
    $relativePath = $Matches[2]
    if ([IO.Path]::IsPathRooted($relativePath) -or $relativePath -match '(^|/)\.\.(/|$)') {
        throw 'Unsafe integrity manifest path.'
    }
    if (-not $manifestPaths.Add($relativePath)) { throw 'Duplicate integrity manifest path.' }
    $candidatePath = (Resolve-Path -LiteralPath (Join-Path $sealedEvidenceDir $relativePath.Replace('/', '\'))).Path
    if (-not $candidatePath.StartsWith($sealedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Integrity manifest path escaped the evidence directory.'
    }
    $candidateItem = Get-Item -Force -LiteralPath $candidatePath
    if ($candidateItem.PSIsContainer -or ($candidateItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Integrity manifest target is not one regular file.'
    }
    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidatePath).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) { throw "Evidence file hash mismatch: $relativePath" }
}

$unexpectedLinks = @(Get-ChildItem -Force -Recurse -LiteralPath $sealedEvidenceDir | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint })
if ($unexpectedLinks.Count -ne 0) { throw 'Sealed evidence tree contains a link or reparse point.' }

$sealedFiles = @(
    Get-ChildItem -Force -Recurse -File -LiteralPath $sealedEvidenceDir |
        Where-Object { $_.FullName -notin @($sealedManifest, (Join-Path $sealedEvidenceDir 'integrity.sha256.anchor')) }
)
if ($sealedFiles.Count -ne $manifestPaths.Count) { throw 'Sealed evidence file set changed.' }
foreach ($file in $sealedFiles) {
    $relativePath = $file.FullName.Substring($sealedEvidenceDir.Length + 1).Replace('\', '/')
    if (-not $manifestPaths.Contains($relativePath)) { throw 'Sealed evidence contains an unlisted file.' }
}
```

## Retention, access, and release result

- Keep the sealed run under the approved security-evidence retention class. The end condition must cover the release lifetime, rollback window, vulnerability remediation, audit requirement, and any legal or incident hold. A calendar date alone must not shorten an active hold.
- Encrypt evidence at rest and in transfer. Use named access, least privilege, multi-factor access where available, and access logging. Do not publish reports or use unrestricted ticket attachments or links.
- Review access at release close and at each retention review. Remove access when an owner leaves the role. Preserve access-log and integrity-anchor history separately from the run directory.
- Do not edit a finding out of a report. Store remediation, false-positive analysis, expiry, compensating control, owner, and approval as a separate record tied to the release commit, affected runtime digest, report hash, finding ID, and evidence anchor.
- Do not delete evidence while a release, rollback, investigation, audit, or hold still needs it. At approved expiry, the evidence custodian must verify the out-of-band anchor, record disposal approval, and use the storage system's exact-object disposal workflow. This runbook provides no broad or recursive delete command.
- Any missing report, parse failure, unexpected scanner exit, invalid or stale Grype database, unreviewed result, High/Critical image finding, secret finding, vulnerable locked dependency, or release-blocking TLS result is no-go.
- A passing record needs the exact commit, all three runtime digests, Python build-base digest, approved source-to-image build record, exact scanner digests and observed versions, requirements hash, Grype database status/checksum, public hostname and external-client label, UTC times, per-image exit codes and report hashes, out-of-band evidence anchor, reviewer, and disposition of every finding.

Repository parsing cannot close this gate. Only execution on the approved scan host against the exact release artifact and real public endpoint creates external scan proof.
