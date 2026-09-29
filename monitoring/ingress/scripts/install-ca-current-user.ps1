[CmdletBinding()]
param(
    [string]$CertificatePath,
    [switch]$Install
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($CertificatePath)) {
    $CertificatePath = Join-Path $PSScriptRoot '..\certs\buet-paas-monitoring-ca.crt'
}

$expectedSha256 = '735C690E91323B973F2069BC1BEB23A5CD4B96F376953D8D56D37196DF8EDE18'
$resolvedPath = (Resolve-Path -LiteralPath $CertificatePath).Path
$certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($resolvedPath)
$sha256 = [System.Security.Cryptography.SHA256]::Create()

try {
    $actualSha256 = ([System.BitConverter]::ToString(
        $sha256.ComputeHash($certificate.RawData)
    )).Replace('-', '')
}
finally {
    $sha256.Dispose()
}

if ($actualSha256 -ne $expectedSha256) {
    throw "CA SHA-256 fingerprint mismatch. Expected $expectedSha256 but found $actualSha256."
}

[pscustomobject]@{
    Subject           = $certificate.Subject
    Issuer            = $certificate.Issuer
    NotBefore         = $certificate.NotBefore.ToUniversalTime().ToString('u')
    NotAfter          = $certificate.NotAfter.ToUniversalTime().ToString('u')
    Sha1Thumbprint    = $certificate.Thumbprint
    Sha256Fingerprint = $actualSha256
    FingerprintMatch  = $true
}

if (-not $Install) {
    Write-Output 'Validation only: the Windows certificate store was not changed.'
    Write-Output 'Run this script again with -Install only after reviewing the fingerprint.'
    exit 0
}

$existing = Get-ChildItem -Path Cert:\CurrentUser\Root |
    Where-Object { $_.Thumbprint -eq $certificate.Thumbprint }

if ($existing) {
    Write-Output 'The exact CA certificate is already trusted for CurrentUser; no duplicate was added.'
    exit 0
}

$imported = Import-Certificate -FilePath $resolvedPath `
    -CertStoreLocation Cert:\CurrentUser\Root

if (-not $imported -or $imported.Thumbprint -ne $certificate.Thumbprint) {
    throw 'Certificate import did not return the expected thumbprint.'
}

Write-Output 'Installed the verified CA certificate in Cert:\CurrentUser\Root.'
Write-Output 'Close and reopen browsers before testing the monitoring URLs.'
