# Trading Bot — Push to GitHub
# Run this once from Windows to upload all code to your GitHub repo.
# Double-click this file or right-click → "Run with PowerShell"

$ErrorActionPreference = "Stop"
$repoPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoPath

Write-Host "=== Trading Bot — GitHub Push ===" -ForegroundColor Cyan
Write-Host "Folder: $repoPath"

# Remove any broken .git from previous attempts
if (Test-Path ".git") {
    Write-Host "Removing old .git folder..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force ".git"
}

# Init fresh repo
git init
git config user.email "tommysn2sm@gmail.com"
git config user.name "Tommysn2"
git branch -M main
git remote add origin https://github.com/Tommysn2/trading-bot.git
git add -A
git commit -m "Initial commit — full trading bot with ICT PM session range module"

Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
Write-Host "(A browser window or credential popup may open — log in with your GitHub account)" -ForegroundColor Yellow
Write-Host ""

git push -u origin main

Write-Host ""
Write-Host "SUCCESS! Code is now at: https://github.com/Tommysn2/trading-bot" -ForegroundColor Green
Read-Host "Press Enter to close"
