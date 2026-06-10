# Build (if needed) and run the FinAlly container on Windows.
# Idempotent: re-running replaces the container but preserves the data volume.
[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$Open
)

$ErrorActionPreference = "Stop"

$Image     = "finally"
$Container = "finally"
$Volume    = "finally-data"
$Port      = 8000
$Url       = "http://localhost:$Port"

# Project root is the parent of this script's directory.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host "No .env found. Copy .env.example to .env and add your OPENROUTER_API_KEY."
    exit 1
}

# Build the image if it's missing or -Build was requested.
docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    Write-Host "Building image '$Image'..."
    docker build -t $Image .
}

# Replace any existing container (data lives in the named volume, not here).
$existing = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch -Pattern $Container
if ($existing) {
    Write-Host "Removing existing container '$Container'..."
    docker rm -f $Container *> $null
}

Write-Host "Starting '$Container' on $Url ..."
docker run -d `
    --name $Container `
    -p "${Port}:8000" `
    -v "${Volume}:/app/db" `
    --env-file .env `
    $Image *> $null

Write-Host "FinAlly is running at $Url"
if ($Open) {
    Start-Process $Url
}
