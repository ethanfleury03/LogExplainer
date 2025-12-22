@echo off
REM Quick SMTP Setup Script for Windows (Batch file)
REM Sets placeholder SMTP environment variables for development

echo Setting up SMTP environment variables (Development Mode)...
echo.

REM Set to Mailtrap's public test server (no auth required for testing)
set SMTP_HOST=smtp.mailtrap.io
set SMTP_PORT=587
set SMTP_USERNAME=
set SMTP_PASSWORD=
set SMTP_USE_TLS=true
set INVITE_FROM_EMAIL=noreply@example.com
set INVITE_FROM_NAME=Arrow Log Helper

echo Environment variables set:
echo   SMTP_HOST = %SMTP_HOST%
echo   SMTP_PORT = %SMTP_PORT%
echo   SMTP_USE_TLS = %SMTP_USE_TLS%
echo   INVITE_FROM_EMAIL = %INVITE_FROM_EMAIL%
echo   INVITE_FROM_NAME = %INVITE_FROM_NAME%
echo.
echo Note: These are placeholder values.
echo For actual email sending, get free Mailtrap credentials at: https://mailtrap.io
echo.
echo To use these variables in this session, run your backend in this same command window.
echo.

