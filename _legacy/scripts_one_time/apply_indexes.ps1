# PowerShell script to apply composite indexes to Vercel Postgres
# Run this script: .\apply_indexes.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "APPLYING COMPOSITE INDEXES (Grok's Recommendation)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Load .env file
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Write-Host "✓ Loaded .env file" -ForegroundColor Green
} else {
    Write-Host "✗ .env file not found!" -ForegroundColor Red
    exit 1
}

$POSTGRES_URL = $env:POSTGRES_URL

if (-not $POSTGRES_URL) {
    Write-Host "✗ POSTGRES_URL not found in environment" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Found POSTGRES_URL" -ForegroundColor Green
Write-Host ""

# Instructions for manual application
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "MANUAL STEPS TO APPLY INDEXES" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Option 1: Via Vercel Dashboard" -ForegroundColor Cyan
Write-Host "  1. Go to: https://vercel.com/familyapps/apestogether/stores" -ForegroundColor White
Write-Host "  2. Click on your Postgres database" -ForegroundColor White
Write-Host "  3. Go to 'Query' tab" -ForegroundColor White
Write-Host "  4. Copy-paste the SQL from add_composite_indexes.sql" -ForegroundColor White
Write-Host "  5. Click 'Execute'" -ForegroundColor White
Write-Host ""
Write-Host "Option 2: Via psql command line" -ForegroundColor Cyan
Write-Host "  psql `"$POSTGRES_URL`" -f add_composite_indexes.sql" -ForegroundColor White
Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "SQL TO RUN (from add_composite_indexes.sql):" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

$sqlContent = Get-Content "add_composite_indexes.sql" -Raw
Write-Host $sqlContent -ForegroundColor White

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "After applying indexes:" -ForegroundColor Cyan
Write-Host "  1. Commit and push code: git push" -ForegroundColor White
Write-Host "  2. Wait ~1 minute for Vercel deployment" -ForegroundColor White
Write-Host "  3. Test: https://apestogether.ai/admin/complete-sept-backfill" -ForegroundColor White
Write-Host "  4. Click '⚡ Bulk Recalc: witty-raven'" -ForegroundColor White
Write-Host ""
Write-Host "Expected: Should complete in <10 seconds (was timing out)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
