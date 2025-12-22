# Setup SMTP Environment Variables for Development
# This script sets SMTP environment variables for the Error Debug email functionality
# Run this script before starting the backend server

Write-Host "Setting up SMTP environment variables for development..." -ForegroundColor Cyan
Write-Host ""

# Option 1: Use Mailtrap (recommended for development/testing)
# Mailtrap is a fake SMTP server that captures emails for testing
# Sign up at https://mailtrap.io (free tier available)
Write-Host "Option 1: Mailtrap (Recommended for Development)" -ForegroundColor Yellow
Write-Host "  - Sign up at https://mailtrap.io (free tier available)" -ForegroundColor Gray
Write-Host "  - Get your credentials from Mailtrap inbox settings" -ForegroundColor Gray
Write-Host ""

# Option 2: Use Gmail (requires app password)
# Write-Host "Option 2: Gmail" -ForegroundColor Yellow
# Write-Host "  - Enable 2FA on your Google account" -ForegroundColor Gray
# Write-Host "  - Generate an app password at https://myaccount.google.com/apppasswords" -ForegroundColor Gray
# Write-Host ""

# Option 3: Use a local SMTP server (like MailHog)
# Write-Host "Option 3: Local SMTP (MailHog)" -ForegroundColor Yellow
# Write-Host "  - Install MailHog: go install github.com/mailhog/MailHog@latest" -ForegroundColor Gray
# Write-Host "  - Run: MailHog" -ForegroundColor Gray
# Write-Host "  - Access UI at http://localhost:8025" -ForegroundColor Gray
# Write-Host ""

# Prompt user for SMTP configuration
$useMailtrap = Read-Host "Use Mailtrap? (Y/n)"
if ($useMailtrap -eq "" -or $useMailtrap -eq "Y" -or $useMailtrap -eq "y") {
    Write-Host ""
    Write-Host "Enter your Mailtrap credentials:" -ForegroundColor Cyan
    $smtpHost = Read-Host "SMTP Host (e.g., smtp.mailtrap.io)"
    $smtpPort = Read-Host "SMTP Port (default: 587)"
    $smtpUsername = Read-Host "SMTP Username"
    $smtpPassword = Read-Host "SMTP Password" -AsSecureString
    $smtpPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPassword)
    )
    
    if ([string]::IsNullOrWhiteSpace($smtpPort)) {
        $smtpPort = "587"
    }
    
    $fromEmail = Read-Host "From Email (default: noreply@example.com)"
    if ([string]::IsNullOrWhiteSpace($fromEmail)) {
        $fromEmail = "noreply@example.com"
    }
    
    $fromName = Read-Host "From Name (default: Arrow Log Helper)"
    if ([string]::IsNullOrWhiteSpace($fromName)) {
        $fromName = "Arrow Log Helper"
    }
} else {
    Write-Host ""
    Write-Host "Enter your SMTP configuration:" -ForegroundColor Cyan
    $smtpHost = Read-Host "SMTP Host"
    $smtpPort = Read-Host "SMTP Port (default: 587)"
    $smtpUsername = Read-Host "SMTP Username (optional)"
    $smtpPassword = Read-Host "SMTP Password (optional)" -AsSecureString
    $smtpPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPassword)
    )
    
    if ([string]::IsNullOrWhiteSpace($smtpPort)) {
        $smtpPort = "587"
    }
    
    $smtpUseTls = Read-Host "Use TLS? (Y/n, default: Y)"
    if ([string]::IsNullOrWhiteSpace($smtpUseTls) -or $smtpUseTls -eq "Y" -or $smtpUseTls -eq "y") {
        $smtpUseTls = "true"
    } else {
        $smtpUseTls = "false"
    }
    
    $fromEmail = Read-Host "From Email (default: noreply@example.com)"
    if ([string]::IsNullOrWhiteSpace($fromEmail)) {
        $fromEmail = "noreply@example.com"
    }
    
    $fromName = Read-Host "From Name (default: Arrow Log Helper)"
    if ([string]::IsNullOrWhiteSpace($fromName)) {
        $fromName = "Arrow Log Helper"
    }
}

# Set environment variables for current session
Write-Host ""
Write-Host "Setting environment variables..." -ForegroundColor Green

$env:SMTP_HOST = $smtpHost
$env:SMTP_PORT = $smtpPort
if (-not [string]::IsNullOrWhiteSpace($smtpUsername)) {
    $env:SMTP_USERNAME = $smtpUsername
}
if (-not [string]::IsNullOrWhiteSpace($smtpPasswordPlain)) {
    $env:SMTP_PASSWORD = $smtpPasswordPlain
}
if ($useMailtrap -ne "" -and ($useMailtrap -eq "Y" -or $useMailtrap -eq "y")) {
    $env:SMTP_USE_TLS = "true"
} else {
    $env:SMTP_USE_TLS = $smtpUseTls
}
$env:INVITE_FROM_EMAIL = $fromEmail
$env:INVITE_FROM_NAME = $fromName

Write-Host ""
Write-Host "Environment variables set for current session:" -ForegroundColor Green
Write-Host "  SMTP_HOST = $env:SMTP_HOST" -ForegroundColor Gray
Write-Host "  SMTP_PORT = $env:SMTP_PORT" -ForegroundColor Gray
if ($env:SMTP_USERNAME) {
    Write-Host "  SMTP_USERNAME = $env:SMTP_USERNAME" -ForegroundColor Gray
}
if ($env:SMTP_PASSWORD) {
    Write-Host "  SMTP_PASSWORD = [HIDDEN]" -ForegroundColor Gray
}
Write-Host "  SMTP_USE_TLS = $env:SMTP_USE_TLS" -ForegroundColor Gray
Write-Host "  INVITE_FROM_EMAIL = $env:INVITE_FROM_EMAIL" -ForegroundColor Gray
Write-Host "  INVITE_FROM_NAME = $env:INVITE_FROM_NAME" -ForegroundColor Gray
Write-Host ""

# Ask if user wants to save to .env file
$saveToEnv = Read-Host "Save to .env file for permanent use? (Y/n)"
if ($saveToEnv -eq "" -or $saveToEnv -eq "Y" -or $saveToEnv -eq "y") {
    $envFile = ".env"
    $envContent = @"
# SMTP Configuration for Error Debug Email Functionality
SMTP_HOST=$smtpHost
SMTP_PORT=$smtpPort
"@
    
    if (-not [string]::IsNullOrWhiteSpace($smtpUsername)) {
        $envContent += "`nSMTP_USERNAME=$smtpUsername"
    }
    if (-not [string]::IsNullOrWhiteSpace($smtpPasswordPlain)) {
        $envContent += "`nSMTP_PASSWORD=$smtpPasswordPlain"
    }
    
    if ($useMailtrap -ne "" -and ($useMailtrap -eq "Y" -or $useMailtrap -eq "y")) {
        $envContent += "`nSMTP_USE_TLS=true"
    } else {
        $envContent += "`nSMTP_USE_TLS=$smtpUseTls"
    }
    
    $envContent += "`nINVITE_FROM_EMAIL=$fromEmail"
    $envContent += "`nINVITE_FROM_NAME=$fromName"
    
    # Check if .env file exists and append or create
    if (Test-Path $envFile) {
        Write-Host ""
        Write-Host ".env file exists. Appending SMTP configuration..." -ForegroundColor Yellow
        # Remove old SMTP vars if they exist
        $existingContent = Get-Content $envFile -Raw
        $lines = $existingContent -split "`n" | Where-Object { 
            $_ -notmatch "^SMTP_" -and $_ -notmatch "^INVITE_FROM_"
        }
        $newContent = ($lines | Where-Object { $_ -ne "" }) -join "`n"
        $newContent += "`n`n# SMTP Configuration`n" + $envContent
        Set-Content -Path $envFile -Value $newContent
    } else {
        Set-Content -Path $envFile -Value $envContent
    }
    
    Write-Host ""
    Write-Host "Configuration saved to .env file!" -ForegroundColor Green
    Write-Host "Note: Make sure your backend loads .env file (using python-dotenv or similar)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To use these variables:" -ForegroundColor Cyan
Write-Host "  1. For current session: Variables are already set" -ForegroundColor Gray
Write-Host "  2. For permanent use: Restart your terminal/IDE after saving to .env" -ForegroundColor Gray
Write-Host "  3. For backend: Make sure your FastAPI app loads .env file" -ForegroundColor Gray
Write-Host ""

