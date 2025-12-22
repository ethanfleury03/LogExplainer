# Verify SMTP Configuration Script
# This script helps verify and test SMTP settings

param(
    [switch]$TestConnection
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SMTP Configuration Verifier" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$envFile = Join-Path $repoRoot ".env"

# Check .env file
Write-Host "[1/3] Checking .env file..." -ForegroundColor Yellow
if (Test-Path $envFile) {
    Write-Host "  Found: $envFile" -ForegroundColor Green
    
    $envContent = Get-Content $envFile -Raw
    $lines = Get-Content $envFile
    
    Write-Host ""
    Write-Host "  Current SMTP Configuration:" -ForegroundColor Cyan
    foreach ($line in $lines) {
        if ($line -match "^SMTP_|^INVITE_FROM_") {
            if ($line -match "PASSWORD") {
                Write-Host "    $($line.Split('=')[0])=[HIDDEN]" -ForegroundColor Gray
            } else {
                Write-Host "    $line" -ForegroundColor Gray
            }
        }
    }
    
    # Extract values
    $smtpHost = ($lines | Where-Object { $_ -match "^SMTP_HOST=" }) -replace "SMTP_HOST=", ""
    $smtpPort = ($lines | Where-Object { $_ -match "^SMTP_PORT=" }) -replace "SMTP_PORT=", ""
    $smtpUsername = ($lines | Where-Object { $_ -match "^SMTP_USERNAME=" }) -replace "SMTP_USERNAME=", ""
    $smtpPassword = ($lines | Where-Object { $_ -match "^SMTP_PASSWORD=" }) -replace "SMTP_PASSWORD=", ""
    $smtpUseTls = ($lines | Where-Object { $_ -match "^SMTP_USE_TLS=" }) -replace "SMTP_USE_TLS=", ""
    $fromEmail = ($lines | Where-Object { $_ -match "^INVITE_FROM_EMAIL=" }) -replace "INVITE_FROM_EMAIL=", ""
    
    # Check for issues
    Write-Host ""
    Write-Host "[2/3] Validating configuration..." -ForegroundColor Yellow
    
    $issues = @()
    if ([string]::IsNullOrWhiteSpace($smtpHost)) { $issues += "SMTP_HOST is missing" }
    if ([string]::IsNullOrWhiteSpace($smtpPort)) { $issues += "SMTP_PORT is missing" }
    if ([string]::IsNullOrWhiteSpace($smtpUsername)) { $issues += "SMTP_USERNAME is missing" }
    if ([string]::IsNullOrWhiteSpace($smtpPassword)) { $issues += "SMTP_PASSWORD is missing" }
    
    if ($issues.Count -gt 0) {
        Write-Host "  Issues found:" -ForegroundColor Red
        foreach ($issue in $issues) {
            Write-Host "    - $issue" -ForegroundColor Red
        }
    } else {
        Write-Host "  All required fields present" -ForegroundColor Green
        
        # Check Gmail-specific issues
        if ($smtpHost -eq "smtp.gmail.com") {
            Write-Host ""
            Write-Host "  Gmail-specific checks:" -ForegroundColor Cyan
            if ($smtpPassword.Length -ne 16 -and $smtpPassword.Length -ne 20) {
                Write-Host "    WARNING: App Password should be 16 characters (no spaces)" -ForegroundColor Yellow
                Write-Host "    Current length: $($smtpPassword.Length)" -ForegroundColor Yellow
            }
            if ($smtpPassword -match " ") {
                Write-Host "    WARNING: App Password contains spaces - remove them!" -ForegroundColor Yellow
            }
            if ($smtpUsername -notmatch "@") {
                Write-Host "    WARNING: Username should be full email address" -ForegroundColor Yellow
            }
        }
    }
    
} else {
    Write-Host "  ERROR: .env file not found at $envFile" -ForegroundColor Red
    Write-Host "  Run: .\setup.ps1" -ForegroundColor Yellow
    exit 1
}

# Test connection if requested
if ($TestConnection) {
    Write-Host ""
    Write-Host "[3/3] Testing SMTP connection..." -ForegroundColor Yellow
    Write-Host "  This will attempt to connect to the SMTP server" -ForegroundColor Gray
    Write-Host ""
    
    $testScript = @"
import smtplib
import sys
import os

# Load from .env
from pathlib import Path
repo_root = Path(r'$repoRoot')
env_file = repo_root / '.env'

if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

smtp_host = os.environ.get('SMTP_HOST')
smtp_port = int(os.environ.get('SMTP_PORT', '587'))
smtp_username = os.environ.get('SMTP_USERNAME')
smtp_password = os.environ.get('SMTP_PASSWORD')
smtp_use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'

if not all([smtp_host, smtp_username, smtp_password]):
    print("ERROR: Missing SMTP configuration")
    sys.exit(1)

try:
    print(f"Connecting to {smtp_host}:{smtp_port}...")
    server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
    
    if smtp_use_tls:
        print("Starting TLS...")
        server.starttls()
    
    print(f"Logging in as {smtp_username}...")
    server.login(smtp_username, smtp_password)
    print("SUCCESS: SMTP connection successful!")
    server.quit()
except smtplib.SMTPAuthenticationError as e:
    print(f"ERROR: Authentication failed - {e}")
    print("")
    print("Common issues:")
    print("  1. For Gmail: Make sure you're using an App Password, not your regular password")
    print("  2. App Password should be exactly 16 characters (no spaces)")
    print("  3. Generate a new App Password at: https://myaccount.google.com/apppasswords")
    print("  4. Make sure 2FA is enabled on your Google account")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: Connection failed - {e}")
    sys.exit(1)
"@
    
    try {
        python -c $testScript
    } catch {
        Write-Host "  ERROR: Failed to run test script" -ForegroundColor Red
        Write-Host "  $_" -ForegroundColor Red
    }
} else {
    Write-Host ""
    Write-Host "[3/3] Skipping connection test" -ForegroundColor Yellow
    Write-Host "  Run with -TestConnection to test SMTP connection" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Verification Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To test SMTP connection:" -ForegroundColor Yellow
Write-Host "  .\scripts\verify-smtp.ps1 -TestConnection" -ForegroundColor White
Write-Host ""

