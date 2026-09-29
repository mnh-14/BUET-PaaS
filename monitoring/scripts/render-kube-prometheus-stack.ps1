[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$HelmPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$chartReference = 'oci://ghcr.io/prometheus-community/charts/kube-prometheus-stack'
$chartVersion = '91.4.1'
$releaseName = 'monitoring-stack'
$releaseNamespace = 'monitoring'
$kubernetesVersion = '1.36.2'
$expectedChartAppVersion = 'v0.94.0'
$expectedOciDigest = 'sha256:e1b65a9105560251ad78b2ef95ad806245e7311a989b60bdbb315c3878bc21d9'

function Invoke-HelmCaptured {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $quotedArguments = $Arguments | ForEach-Object {
        '"' + $_.Replace('"', '\"') + '"'
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $HelmPath
    $startInfo.Arguments = $quotedArguments -join ' '
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw 'Failed to start Helm.'
    }

    $standardOutput = $process.StandardOutput.ReadToEnd()
    $standardError = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = (($standardOutput, $standardError) -join '').TrimEnd()
    }
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$valuesPath = Join-Path $repositoryRoot 'monitoring\prometheus\values.yaml'

if (-not (Test-Path -LiteralPath $HelmPath -PathType Leaf)) {
    throw "Helm executable not found: $HelmPath"
}

if (-not (Test-Path -LiteralPath $valuesPath -PathType Leaf)) {
    throw "Values file not found: $valuesPath"
}

New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$resolvedOutputDirectory = (Resolve-Path -LiteralPath $OutputDirectory).Path
$chartArchive = Join-Path $resolvedOutputDirectory "kube-prometheus-stack-$chartVersion.tgz"
$chartMetadata = Join-Path $resolvedOutputDirectory 'chart-metadata.yaml'
$chartDefaults = Join-Path $resolvedOutputDirectory 'chart-default-values.yaml'
$renderedManifest = Join-Path $resolvedOutputDirectory 'rendered.yaml'
$lintOutput = Join-Path $resolvedOutputDirectory 'helm-lint.txt'
$pullOutput = Join-Path $resolvedOutputDirectory 'helm-pull.txt'
$hashOutput = Join-Path $resolvedOutputDirectory 'sha256.txt'

& $HelmPath version --short
if ($LASTEXITCODE -ne 0) {
    throw 'helm version failed.'
}

$pullResult = Invoke-HelmCaptured -Arguments @(
    'pull', $chartReference,
    '--version', $chartVersion,
    '--destination', $resolvedOutputDirectory
)
$pullResult.Output | Tee-Object -FilePath $pullOutput
if ($pullResult.ExitCode -ne 0) {
    throw 'helm pull failed.'
}

$pullText = Get-Content -LiteralPath $pullOutput -Raw
if ($pullText -notmatch [regex]::Escape($expectedOciDigest)) {
    throw "OCI digest did not match the expected publisher digest $expectedOciDigest."
}

& $HelmPath show chart $chartArchive | Set-Content -Encoding utf8 -LiteralPath $chartMetadata
if ($LASTEXITCODE -ne 0) {
    throw 'helm show chart failed.'
}

$metadataText = Get-Content -LiteralPath $chartMetadata -Raw
if ($metadataText -notmatch "(?m)^version:\s+$([regex]::Escape($chartVersion))\s*$") {
    throw "Chart metadata version is not $chartVersion."
}
if ($metadataText -notmatch "(?m)^appVersion:\s+$([regex]::Escape($expectedChartAppVersion))\s*$") {
    throw "Chart appVersion is not $expectedChartAppVersion."
}

& $HelmPath show values $chartArchive | Set-Content -Encoding utf8 -LiteralPath $chartDefaults
if ($LASTEXITCODE -ne 0) {
    throw 'helm show values failed.'
}

$lintResult = Invoke-HelmCaptured -Arguments @(
    'lint', $chartArchive,
    '--values', $valuesPath,
    '--kube-version', $kubernetesVersion
)
$lintResult.Output | Tee-Object -FilePath $lintOutput
if ($lintResult.ExitCode -ne 0) {
    throw 'helm lint failed.'
}

& $HelmPath template $releaseName $chartArchive `
    --namespace $releaseNamespace `
    --values $valuesPath `
    --kube-version $kubernetesVersion `
    --include-crds |
    Set-Content -Encoding utf8 -LiteralPath $renderedManifest
if ($LASTEXITCODE -ne 0) {
    throw 'helm template failed.'
}

Get-FileHash -Algorithm SHA256 -LiteralPath $valuesPath, $chartArchive, $renderedManifest |
    ForEach-Object { "{0}  {1}" -f $_.Hash.ToLowerInvariant(), $_.Path } |
    Set-Content -Encoding utf8 -LiteralPath $hashOutput

Write-Output "Rendered manifest: $renderedManifest"
Write-Output "Chart metadata:    $chartMetadata"
Write-Output "Chart defaults:    $chartDefaults"
Write-Output "Hashes:            $hashOutput"
