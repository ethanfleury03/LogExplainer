# Unified Backend Setup Script
# This script sets up everything needed for the backend to run

param(
    [switch]$SkipSMTP,
    [switch]$SkipDependencies
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Backend Setup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get script directory (root of repo)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Step 1: Check Python
Write-Host "[1/5] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  Found: $pythonVersion" -ForegroundColor Green
    
    # Check if Python 3.8+
    $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
    if ($versionMatch) {
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 8)) {
            Write-Host "  WARNING: Python 3.8+ recommended" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "  ERROR: Python not found!" -ForegroundColor Red
    Write-Host "  Please install Python 3.8+ from https://www.python.org/" -ForegroundColor Yellow
    exit 1
}

# Step 2: Check/create virtual environment
Write-Host ""
Write-Host "[2/5] Checking virtual environment..." -ForegroundColor Yellow
$venvPath = Join-Path $scriptDir ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "  Creating virtual environment..." -ForegroundColor Gray
    python -m venv .venv
    Write-Host "  Virtual environment created" -ForegroundColor Green
} else {
    Write-Host "  Virtual environment exists" -ForegroundColor Green
}

# Activate virtual environment
Write-Host "  Activating virtual environment..." -ForegroundColor Gray
& "$venvPath\Scripts\Activate.ps1"

# Step 3: Install dependencies
if (-not $SkipDependencies) {
    Write-Host ""
    Write-Host "[3/5] Installing Python dependencies..." -ForegroundColor Yellow
    $requirementsPath = Join-Path $scriptDir "backend\requirements.txt"
    if (Test-Path $requirementsPath) {
        Write-Host "  Installing from backend\requirements.txt..." -ForegroundColor Gray
        pip install -q --upgrade pip
        pip install -q -r $requirementsPath
        Write-Host "  Dependencies installed" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: backend\requirements.txt not found" -ForegroundColor Yellow
    }
} else {
    Write-Host ""
    Write-Host "[3/5] Skipping dependency installation (--SkipDependencies)" -ForegroundColor Yellow
}

# Step 4: Initialize database
Write-Host ""
Write-Host "[4/5] Initializing database..." -ForegroundColor Yellow
$dbPath = Join-Path $scriptDir "dev_storage\error_debug.db"
$dbDir = Split-Path $dbPath -Parent
if (-not (Test-Path $dbDir)) {
    New-Item -ItemType Directory -Path $dbDir -Force | Out-Null
    Write-Host "  Created dev_storage directory" -ForegroundColor Gray
}

# Run database initialization
try {
    $initScript = @"
import sys
import os
sys.path.insert(0, r'$scriptDir')
os.chdir(r'$scriptDir')
from backend.utils.db import init_db
init_db()
print('Database initialized successfully')
"@
    python -c $initScript
    Write-Host "  Database initialized" -ForegroundColor Green
} catch {
    Write-Host "  WARNING: Database initialization failed (may already exist)" -ForegroundColor Yellow
    Write-Host "  Error: $_" -ForegroundColor Gray
}

# Step 5: SMTP Configuration
if (-not $SkipSMTP) {
    Write-Host ""
    Write-Host "[5/5] Configuring SMTP..." -ForegroundColor Yellow
    Write-Host ""
    
    $envFile = Join-Path $scriptDir ".env"
    $hasExistingEnv = Test-Path $envFile
    
    if ($hasExistingEnv) {
        $existingContent = Get-Content $envFile -Raw
        if ($existingContent -match "SMTP_HOST") {
            Write-Host "  SMTP configuration found in .env file" -ForegroundColor Green
            $update = Read-Host "  Update SMTP configuration? (y/N)"
            if ($update -ne "y" -and $update -ne "Y") {
                Write-Host "  Keeping existing SMTP configuration" -ForegroundColor Gray
                $skipSMTP = $true
            }
        }
    }
    
    if (-not $skipSMTP) {
        Write-Host "  SMTP Setup Options:" -ForegroundColor Cyan
        Write-Host "    1. Mailtrap (Recommended for development)" -ForegroundColor White
        Write-Host "    2. Gmail (Requires App Password)" -ForegroundColor White
        Write-Host "    3. Skip SMTP setup" -ForegroundColor White
        Write-Host ""
        
        $smtpChoice = Read-Host "  Choose option (1-3, default: 3)"
        
        if ($smtpChoice -eq "1") {
            # Mailtrap setup
            Write-Host ""
            Write-Host "  Mailtrap Setup:" -ForegroundColor Cyan
            Write-Host "  Sign up at https://mailtrap.io (free tier available)" -ForegroundColor Gray
            Write-Host "  Get credentials from Mailtrap inbox settings" -ForegroundColor Gray
            Write-Host ""
            
            $smtpHost = Read-Host "  SMTP Host (default: smtp.mailtrap.io)"
            if ([string]::IsNullOrWhiteSpace($smtpHost)) { $smtpHost = "smtp.mailtrap.io" }
            
            $smtpPort = Read-Host "  SMTP Port (default: 587)"
            if ([string]::IsNullOrWhiteSpace($smtpPort)) { $smtpPort = "587" }
            
            $smtpUsername = Read-Host "  SMTP Username"
            $smtpPassword = Read-Host "  SMTP Password" -AsSecureString
            $smtpPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPassword)
            )
            
            $fromEmail = Read-Host "  From Email (default: noreply@example.com)"
            if ([string]::IsNullOrWhiteSpace($fromEmail)) { $fromEmail = "noreply@example.com" }
            
            $fromName = Read-Host "  From Name (default: Arrow Log Helper)"
            if ([string]::IsNullOrWhiteSpace($fromName)) { $fromName = "Arrow Log Helper" }
            
            $envContent = @"
# SMTP Configuration
SMTP_HOST=$smtpHost
SMTP_PORT=$smtpPort
SMTP_USERNAME=$smtpUsername
SMTP_PASSWORD=$smtpPasswordPlain
SMTP_USE_TLS=true
INVITE_FROM_EMAIL=$fromEmail
INVITE_FROM_NAME=$fromName
"@
            
        } elseif ($smtpChoice -eq "2") {
            # Gmail setup
            Write-Host ""
            Write-Host "  Gmail Setup:" -ForegroundColor Cyan
            Write-Host "  IMPORTANT: You need a Gmail App Password, not your regular password!" -ForegroundColor Yellow
            Write-Host "  Generate one at: https://myaccount.google.com/apppasswords" -ForegroundColor Gray
            Write-Host ""
            
            $gmailAddress = Read-Host "  Gmail Address (e.g., ethan@arrsys.com)"
            $appPassword = Read-Host "  App Password (16 characters, no spaces)" -AsSecureString
            $appPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPassword)
            )
            
            $fromName = Read-Host "  From Name (default: Arrow Systems Support)"
            if ([string]::IsNullOrWhiteSpace($fromName)) { $fromName = "Arrow Systems Support" }
            
            $envContent = @"
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=$gmailAddress
SMTP_PASSWORD=$appPasswordPlain
SMTP_USE_TLS=true
INVITE_FROM_EMAIL=$gmailAddress
INVITE_FROM_NAME=$fromName
"@
            
        } else {
            Write-Host "  Skipping SMTP configuration" -ForegroundColor Gray
            $envContent = $null
        }
        
        if ($envContent) {
            # Update or create .env file
            if ($hasExistingEnv) {
                $existingContent = Get-Content $envFile -Raw
                $lines = $existingContent -split "`n" | Where-Object { 
                    $_ -notmatch "^SMTP_" -and $_ -notmatch "^INVITE_FROM_" -and $_ -notmatch "^# SMTP"
                }
                $newContent = ($lines | Where-Object { $_ -ne "" -and $_ -notmatch "^\s*$" }) -join "`n"
                if ($newContent) {
                    $newContent += "`n`n"
                }
                $newContent += $envContent
                Set-Content -Path $envFile -Value $newContent
            } else {
                Set-Content -Path $envFile -Value $envContent
            }
            Write-Host "  SMTP configuration saved to .env file" -ForegroundColor Green
        }
    }
} else {
    Write-Host ""
    Write-Host "[5/5] Skipping SMTP configuration (--SkipSMTP)" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Start the backend server:" -ForegroundColor White
Write-Host "     cd backend" -ForegroundColor Gray
Write-Host "     python -m uvicorn main:app --reload --port 8000" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Start the frontend (in another terminal):" -ForegroundColor White
Write-Host "     cd frontend\analyzer" -ForegroundColor Gray
Write-Host "     npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Open http://localhost:3000 in your browser" -ForegroundColor White
Write-Host ""

