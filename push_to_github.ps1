# Trading Bot -- Push latest changes to GitHub
# Run this whenever you want to sync local changes to the repo.
# Railway auto-deploys when GitHub is updated.

$ErrorActionPreference = "Stop"
$repoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoPath

Write-Host "=== Trading Bot - GitHub Push ===" -ForegroundColor Cyan
Write-Host "Folder: $repoPath"
Write-Host ""

# Stage all changes
git add -A

# Check if there's anything to commit
$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit -- already up to date." -ForegroundColor Green
    Read-Host "Press Enter to close"
    exit 0
}

# Commit with timestamp
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
git commit -m "Update - $timestamp"

Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git push

Write-Host ""
Write-Host "SUCCESS! Changes pushed to GitHub." -ForegroundColor Green
Write-Host "Railway will auto-redeploy in ~30 seconds." -ForegroundColor Yellow
Read-Host "Press Enter to close"
