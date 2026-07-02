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

# Commit any new local changes (skip if nothing to commit)
$status = git status --porcelain
if ($status) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    git commit -m "Update - $timestamp"
} else {
    Write-Host "Nothing new to commit." -ForegroundColor Yellow
}

# Always push -- commits made by Claude in the background also need pushing
Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git push

Write-Host ""
Write-Host "SUCCESS! Changes pushed to GitHub." -ForegroundColor Green
Write-Host "Railway will auto-redeploy in ~30 seconds." -ForegroundColor Yellow
Read-Host "Press Enter to close"
