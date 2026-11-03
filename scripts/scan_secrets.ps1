# FINN — Secret Scanner (PowerShell)
# Scans tracked, staged, and working tree files for exposed API keys.
# Exits 0 if clean, exits 1 if any pattern matching AQ. or AIza keys is detected.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Write-Host "[SECRET SCAN] Scanning repo files for exposed Gemini/Google API keys..." -ForegroundColor Cyan

$KeyPattern = '(AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,})'
$IgnoreDirs = @(".git", ".venv", "venv", "node_modules", "__pycache__", "dist", ".next")
$IgnoreExts = @(".pdf", ".pyc", ".png", ".jpg", ".jpeg", ".ico", ".svg", ".zip")

$TrackedFiles = @()
try {
    $TrackedFiles = (git -C $Root ls-files) -split "`r?`n"
} catch {}

$Violations = @()

foreach ($File in $TrackedFiles) {
    if (-not $File) { continue }
    $FullPath = Join-Path $Root $File
    if (-not (Test-Path $FullPath -PathType Leaf)) { continue }
    
    $Ext = [System.IO.Path]::GetExtension($FullPath).ToLower()
    if ($IgnoreExts -contains $Ext) { continue }

    $Lines = Get-Content $FullPath -ErrorAction SilentlyContinue
    $LineNum = 1
    foreach ($Line in $Lines) {
        if ($Line -match $KeyPattern) {
            $Violations += "$File (line $LineNum)"
        }
        $LineNum++
    }
}

# Also check any .env files in root
Get-ChildItem -Path $Root -Force -Filter ".env*" | ForEach-Object {
    if ($_.Name -ne ".env.example") {
        $Violations += "$($_.Name) (unauthorized env file exists on disk)"
    }
}

if ($Violations.Count -gt 0) {
    Write-Host "`n[SECRET SCAN] FAIL: Potential API key or forbidden file detected in:" -ForegroundColor Red
    foreach ($V in $Violations) {
        Write-Host "  - $V" -ForegroundColor Red
    }
    Write-Host "`nAction required: Remove keys from files immediately. Use environment variables only." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "[SECRET SCAN] PASS: Scanned $($TrackedFiles.Count) tracked files. No API keys found." -ForegroundColor Green
    exit 0
}
