# Stop and remove the FinAlly container (Windows).
# The named volume 'finally-data' is preserved, so the database survives.
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Container = "finally"

$existing = docker ps -a --format '{{.Names}}' | Select-String -SimpleMatch -Pattern $Container
if ($existing) {
    Write-Host "Stopping and removing '$Container'..."
    docker rm -f $Container *> $null
    Write-Host "Stopped. Data volume 'finally-data' preserved."
} else {
    Write-Host "Container '$Container' is not running."
}
