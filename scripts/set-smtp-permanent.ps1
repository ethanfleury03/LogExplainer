# Set SMTP Configuration Permanently
# This script helps you set SMTP configuration that will never change

param(
    [string]$SmtpHost,
    [string]$Port = "587",
    [string]$Username,
    [string]$Password,
    [string]$FromEmail,
    [string]$FromName = "Arrow Systems Support",
    [switch]$Gmail
)

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Permanent SMTP Configuration" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$envFile = Join-Path $repoRoot ".env"

# Gmail mode
if ($Gmail) {
    Write-Host "Gmail Configuration Mode" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "IMPORTANT: You need a Gmail App Password!" -ForegroundColor Yellow
    Write-Host "  1. Go to: https://myaccount.google.com/apppasswords" -ForegroundColor White
    Write-Host "  2. Select 'Mail' and 'Other (Custom name)'" -ForegroundColor White
    Write-Host "  3. Enter name: 'Error Debug App'" -ForegroundColor White
    Write-Host "  4. Copy the 16-character password (remove spaces if any)" -ForegroundColor White
    Write-Host ""
    
    if (-not $Username) {
        $Username = Read-Host "Gmail Address (e.g., ethan@arrsys.com)"
    }
    
    if (-not $Password) {
        $passwordSecure = Read-Host "App Password (16 characters, no spaces)" -AsSecureString
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
        )
    } elseif ($Password -is [SecureString]) {
        # Convert SecureString to plain string if it was passed as SecureString
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
        )
    }
    
    $SmtpHost = "smtp.gmail.com"
    $Port = "587"
    $FromEmail = $Username
    $FromName = "Arrow Systems Support"
    
} else {
    # Manual configuration
    if (-not $SmtpHost) {
        $SmtpHost = Read-Host "SMTP Host"
    }
    if (-not $Port) {
        $Port = Read-Host "SMTP Port (default: 587)"
        if ([string]::IsNullOrWhiteSpace($Port)) { $Port = "587" }
    }
    if (-not $Username) {
        $Username = Read-Host "SMTP Username"
    }
    if (-not $Password) {
        $passwordSecure = Read-Host "SMTP Password" -AsSecureString
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
        )
    } elseif ($Password -is [SecureString]) {
        # Convert SecureString to plain string if it was passed as SecureString
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
        )
    }
    if (-not $FromEmail) {
        $FromEmail = Read-Host "From Email"
    }
    if (-not $FromName) {
        $FromName = Read-Host "From Name (default: Arrow Systems Support)"
        if ([string]::IsNullOrWhiteSpace($FromName)) { $FromName = "Arrow Systems Support" }
    }
}

# Validate
if ([string]::IsNullOrWhiteSpace($SmtpHost) -or 
    [string]::IsNullOrWhiteSpace($Username) -or 
    [string]::IsNullOrWhiteSpace($Password)) {
    Write-Host ""
    Write-Host "ERROR: Missing required fields!" -ForegroundColor Red
    exit 1
}

# For Gmail, validate App Password format
if ($SmtpHost -eq "smtp.gmail.com") {
    # Remove any spaces from password
    $Password = $Password -replace '\s', ''
    
    if ($Password.Length -ne 16) {
        Write-Host ""
        Write-Host "WARNING: Gmail App Password should be exactly 16 characters" -ForegroundColor Yellow
        Write-Host "  Current length: $($Password.Length)" -ForegroundColor Yellow
        $continue = Read-Host "  Continue anyway? (y/N)"
        if ($continue -ne "y" -and $continue -ne "Y") {
            exit 1
        }
    }
}

# Build .env content
$envContent = @"
# SMTP Configuration (Permanent)
# DO NOT MODIFY - Set via scripts/set-smtp-permanent.ps1
SMTP_HOST=$SmtpHost
SMTP_PORT=$Port
SMTP_USERNAME=$Username
SMTP_PASSWORD=$Password
SMTP_USE_TLS=true
INVITE_FROM_EMAIL=$FromEmail
INVITE_FROM_NAME=$FromName
"@

# Read existing .env and preserve non-SMTP variables
if (Test-Path $envFile) {
    $existingContent = Get-Content $envFile -Raw
    $lines = $existingContent -split "`n" | Where-Object { 
        $_ -notmatch "^SMTP_" -and $_ -notmatch "^INVITE_FROM_" -and $_ -notmatch "^# SMTP"
    }
    $otherContent = ($lines | Where-Object { $_ -ne "" -and $_ -notmatch "^\s*$" }) -join "`n"
    
    if ($otherContent) {
        $newContent = $otherContent + "`n`n" + $envContent
    } else {
        $newContent = $envContent
    }
} else {
    $newContent = $envContent
}

# Write to .env file
Set-Content -Path $envFile -Value $newContent -Encoding UTF8

Write-Host ""
Write-Host "Configuration saved to .env file!" -ForegroundColor Green
Write-Host ""
Write-Host "Settings:" -ForegroundColor Cyan
Write-Host "  SMTP_HOST = $SmtpHost" -ForegroundColor Gray
Write-Host "  SMTP_PORT = $Port" -ForegroundColor Gray
Write-Host "  SMTP_USERNAME = $Username" -ForegroundColor Gray
Write-Host "  SMTP_PASSWORD = [SET]" -ForegroundColor Gray
Write-Host "  INVITE_FROM_EMAIL = $FromEmail" -ForegroundColor Gray
Write-Host "  INVITE_FROM_NAME = $FromName" -ForegroundColor Gray
Write-Host ""

# Test connection
$test = Read-Host "Test SMTP connection now? (Y/n)"
if ($test -eq "" -or $test -eq "Y" -or $test -eq "y") {
    Write-Host ""
    Write-Host "Testing connection..." -ForegroundColor Yellow
    
    # Create temporary Python script file
    $tempScript = Join-Path $env:TEMP "test_smtp_$(Get-Random).py"
    
    $pythonCode = @"
import smtplib
import sys
import os
from pathlib import Path

repo_root = Path(r"$repoRoot")
env_file = repo_root / ".env"

if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

smtp_host = os.environ.get("SMTP_HOST")
smtp_port = int(os.environ.get("SMTP_PORT", "587"))
smtp_username = os.environ.get("SMTP_USERNAME")
smtp_password = os.environ.get("SMTP_PASSWORD")
smtp_use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

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
    print(f"ERROR: Authentication failed")
    print(f"Details: {e}")
    print("")
    print("For Gmail:")
    print("  1. Make sure you're using an App Password (not regular password)")
    print("  2. App Password should be exactly 16 characters (no spaces)")
    print("  3. Generate new at: https://myaccount.google.com/apppasswords")
    print("  4. Make sure 2FA is enabled")
    sys.exit(1)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
"@
    
    try {
        Set-Content -Path $tempScript -Value $pythonCode -Encoding UTF8
        python $tempScript
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    } catch {
        Write-Host "  ERROR: Failed to run test script" -ForegroundColor Red
        Write-Host "  $_" -ForegroundColor Red
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    }
}
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "SUCCESS: SMTP configuration is working!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "FAILED: Please check your credentials" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. RESTART your backend server" -ForegroundColor White
Write-Host "  2. Try sending an email again" -ForegroundColor White
Write-Host ""
Write-Host "To verify configuration later:" -ForegroundColor Yellow
Write-Host "  .\scripts\verify-smtp.ps1 -TestConnection" -ForegroundColor White
Write-Host ""

