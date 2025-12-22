# Quick Mailtrap Setup
# Mailtrap is the easiest option for development/testing

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Mailtrap SMTP Setup (Easiest Option)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Mailtrap is perfect for development because:" -ForegroundColor Yellow
Write-Host "  ✓ No App Passwords needed" -ForegroundColor Green
Write-Host "  ✓ No 2FA required" -ForegroundColor Green
Write-Host "  ✓ Free tier available" -ForegroundColor Green
Write-Host "  ✓ Emails are captured (not actually sent)" -ForegroundColor Green
Write-Host "  ✓ View emails in web interface" -ForegroundColor Green
Write-Host ""

$useMailtrap = Read-Host "Do you already have a Mailtrap account? (Y/n)"
if ($useMailtrap -ne "Y" -and $useMailtrap -ne "y" -and $useMailtrap -ne "") {
    Write-Host ""
    Write-Host "Sign up for free at: https://mailtrap.io" -ForegroundColor Cyan
    Write-Host "Then run this script again." -ForegroundColor Yellow
    Write-Host ""
    exit 0
}

Write-Host ""
Write-Host "Get your Mailtrap credentials:" -ForegroundColor Cyan
Write-Host "  1. Go to https://mailtrap.io and sign in" -ForegroundColor White
Write-Host "  2. Create an inbox (or use existing)" -ForegroundColor White
Write-Host "  3. Go to inbox settings -> SMTP Settings" -ForegroundColor White
Write-Host "  4. Copy the credentials shown" -ForegroundColor White
Write-Host ""

$smtpHost = Read-Host "SMTP Host (default: smtp.mailtrap.io)"
if ([string]::IsNullOrWhiteSpace($smtpHost)) { $smtpHost = "smtp.mailtrap.io" }

$smtpPort = Read-Host "SMTP Port (default: 587)"
if ([string]::IsNullOrWhiteSpace($smtpPort)) { $smtpPort = "587" }

$smtpUsername = Read-Host "SMTP Username (from Mailtrap)"
$smtpPassword = Read-Host "SMTP Password (from Mailtrap)" -AsSecureString
$smtpPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($smtpPassword)
)

$fromEmail = Read-Host "From Email (default: noreply@example.com)"
if ([string]::IsNullOrWhiteSpace($fromEmail)) { $fromEmail = "noreply@example.com" }

$fromName = Read-Host "From Name (default: Arrow Systems Support)"
if ([string]::IsNullOrWhiteSpace($fromName)) { $fromName = "Arrow Systems Support" }

# Build .env content
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$envFile = Join-Path $repoRoot ".env"

$envContent = @"
# SMTP Configuration (Mailtrap - Development/Testing)
# DO NOT MODIFY - Set via scripts/setup-mailtrap-quick.ps1
SMTP_HOST=$smtpHost
SMTP_PORT=$smtpPort
SMTP_USERNAME=$smtpUsername
SMTP_PASSWORD=$smtpPasswordPlain
SMTP_USE_TLS=true
INVITE_FROM_EMAIL=$fromEmail
INVITE_FROM_NAME=$fromName
"@

# Read existing .env and preserve non-SMTP variables
if (Test-Path $envFile) {
    $existingContent = Get-Content $envFile -Raw
    $newline = [Environment]::NewLine
    $lines = $existingContent -split $newline | Where-Object { 
        $_ -notmatch '^SMTP_' -and $_ -notmatch '^INVITE_FROM_' -and $_ -notmatch '^#.*SMTP'
    }
    $otherContent = ($lines | Where-Object { $_ -ne "" -and $_ -notmatch "^\s*$" }) -join $newline
    
    if ($otherContent) {
        $newContent = $otherContent + $newline + $newline + $envContent
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
Write-Host "  SMTP_HOST = $smtpHost" -ForegroundColor Gray
Write-Host "  SMTP_PORT = $smtpPort" -ForegroundColor Gray
Write-Host "  SMTP_USERNAME = $smtpUsername" -ForegroundColor Gray
Write-Host "  SMTP_PASSWORD = [SET]" -ForegroundColor Gray
Write-Host "  INVITE_FROM_EMAIL = $fromEmail" -ForegroundColor Gray
Write-Host "  INVITE_FROM_NAME = $fromName" -ForegroundColor Gray
Write-Host ""

# Test connection
$test = Read-Host "Test SMTP connection now? (Y/n)"
if ($test -eq "" -or $test -eq "Y" -or $test -eq "y") {
    Write-Host ""
    Write-Host "Testing connection..." -ForegroundColor Yellow
    
    # Create temporary Python script file
    $tempScript = Join-Path $env:TEMP "test_smtp_$(Get-Random).py"
    
    # Build Python code line by line to avoid PowerShell parsing issues
    $pythonLines = @()
    $pythonLines += 'import smtplib'
    $pythonLines += 'import sys'
    $pythonLines += 'import os'
    $pythonLines += 'from pathlib import Path'
    $pythonLines += ''
    $pythonLines += "repo_root = Path(r'$repoRoot')"
    $pythonLines += "env_file = repo_root / '.env'"
    $pythonLines += ''
    $pythonLines += 'if env_file.exists():'
    $pythonLines += '    from dotenv import load_dotenv'
    $pythonLines += '    load_dotenv(env_file)'
    $pythonLines += ''
    $pythonLines += "smtp_host = os.environ.get('SMTP_HOST')"
    $pythonLines += "smtp_port = int(os.environ.get('SMTP_PORT', '587'))"
    $pythonLines += "smtp_username = os.environ.get('SMTP_USERNAME')"
    $pythonLines += "smtp_password = os.environ.get('SMTP_PASSWORD')"
    $pythonLines += "smtp_use_tls = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'"
    $pythonLines += ''
    $pythonLines += 'try:'
    $pythonLines += '    print(f"Connecting to {smtp_host}:{smtp_port}...")'
    $pythonLines += '    server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)'
    $pythonLines += '    '
    $pythonLines += '    if smtp_use_tls:'
    $pythonLines += '        print("Starting TLS...")'
    $pythonLines += '        server.starttls()'
    $pythonLines += '    '
    $pythonLines += '    print(f"Logging in as {smtp_username}...")'
    $pythonLines += '    server.login(smtp_username, smtp_password)'
    $pythonLines += '    print("SUCCESS: SMTP connection successful!")'
    $pythonLines += '    print("")'
    $pythonLines += '    print("Your emails will be captured in Mailtrap inbox (not actually sent)")'
    $pythonLines += '    server.quit()'
    $pythonLines += 'except Exception as e:'
    $pythonLines += '    print(f"ERROR: {e}")'
    $pythonLines += '    sys.exit(1)'
    
    $pythonCode = $pythonLines -join [Environment]::NewLine
    
    try {
        Set-Content -Path $tempScript -Value $pythonCode -Encoding UTF8
        python $tempScript
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    } catch {
        Write-Host "  ERROR: Failed to run test script" -ForegroundColor Red
        Write-Host "  $_" -ForegroundColor Red
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    }
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "SUCCESS: SMTP configuration is working!" -ForegroundColor Green
        Write-Host ""
        Write-Host "View captured emails at: https://mailtrap.io/inboxes" -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "FAILED: Please check your Mailtrap credentials" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. RESTART your backend server" -ForegroundColor White
Write-Host "  2. Try sending an email - it will appear in your Mailtrap inbox" -ForegroundColor White
Write-Host "  3. View emails at: https://mailtrap.io/inboxes" -ForegroundColor White
Write-Host ""

