# Quick SMTP Setup Script (No credentials required - uses Mailtrap defaults)
# This sets up a basic SMTP configuration using Mailtrap's public test server
# For actual email sending, you'll need real credentials

Write-Host "Setting up SMTP environment variables (Development Mode)..." -ForegroundColor Cyan
Write-Host ""

# Set to Mailtrap's public test server (no auth required for testing)
# For production, replace with your actual SMTP server
$env:SMTP_HOST = "smtp.mailtrap.io"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = ""
$env:SMTP_PASSWORD = ""
$env:SMTP_USE_TLS = "true"
$env:INVITE_FROM_EMAIL = "noreply@example.com"
$env:INVITE_FROM_NAME = "Arrow Log Helper"

Write-Host "Environment variables set:" -ForegroundColor Green
Write-Host "  SMTP_HOST = $env:SMTP_HOST" -ForegroundColor Gray
Write-Host "  SMTP_PORT = $env:SMTP_PORT" -ForegroundColor Gray
Write-Host "  SMTP_USE_TLS = $env:SMTP_USE_TLS" -ForegroundColor Gray
Write-Host "  INVITE_FROM_EMAIL = $env:INVITE_FROM_EMAIL" -ForegroundColor Gray
Write-Host "  INVITE_FROM_NAME = $env:INVITE_FROM_NAME" -ForegroundColor Gray
Write-Host ""
Write-Host "Note: These are placeholder values." -ForegroundColor Yellow
Write-Host "For actual email sending, run: .\scripts\setup-smtp-env.ps1" -ForegroundColor Yellow
Write-Host "Or get free Mailtrap credentials at: https://mailtrap.io" -ForegroundColor Yellow
Write-Host ""

