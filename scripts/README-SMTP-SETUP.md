# SMTP Setup for Error Debug Email Functionality

This guide helps you set up SMTP environment variables for the email script functionality.

## Quick Setup (No Credentials)

If you just want to test the UI without actually sending emails:

```powershell
.\scripts\setup-smtp-env-simple.ps1
```

This sets placeholder values. The backend will show a helpful error message if you try to send emails.

## Full Setup (With Real SMTP)

### Option 1: Interactive Setup Script

Run the interactive setup script:

```powershell
.\scripts\setup-smtp-env.ps1
```

This will:
- Prompt you for SMTP credentials
- Set environment variables for the current session
- Optionally save to `.env` file for permanent use

### Option 2: Manual Setup

#### For Current Session (PowerShell)

```powershell
$env:SMTP_HOST = "smtp.mailtrap.io"
$env:SMTP_PORT = "587"
$env:SMTP_USERNAME = "your-username"
$env:SMTP_PASSWORD = "your-password"
$env:SMTP_USE_TLS = "true"
$env:INVITE_FROM_EMAIL = "noreply@example.com"
$env:INVITE_FROM_NAME = "Arrow Log Helper"
```

#### For Permanent Setup (.env file)

Create a `.env` file in the `backend/` directory:

```env
SMTP_HOST=smtp.mailtrap.io
SMTP_PORT=587
SMTP_USERNAME=your-username
SMTP_PASSWORD=your-password
SMTP_USE_TLS=true
INVITE_FROM_EMAIL=noreply@example.com
INVITE_FROM_NAME=Arrow Log Helper
```

Then make sure your backend loads the `.env` file (see Backend Configuration below).

## SMTP Service Options

### Mailtrap (Recommended for Development)

1. Sign up at https://mailtrap.io (free tier available)
2. Create an inbox
3. Go to inbox settings → SMTP Settings
4. Copy the credentials:
   - Host: `smtp.mailtrap.io`
   - Port: `587` (or `2525`)
   - Username: (from Mailtrap)
   - Password: (from Mailtrap)

**Benefits:**
- Free tier available
- Captures emails (doesn't actually send them)
- Perfect for development/testing
- No risk of sending test emails to real addresses

### Gmail

1. Enable 2FA on your Google account
2. Generate an app password: https://myaccount.google.com/apppasswords
3. Use these settings:
   - Host: `smtp.gmail.com`
   - Port: `587`
   - Username: Your Gmail address
   - Password: The app password (not your regular password)

### Local SMTP (MailHog)

For completely local testing:

1. Install MailHog:
   ```bash
   go install github.com/mailhog/MailHog@latest
   ```

2. Run MailHog:
   ```bash
   MailHog
   ```

3. Use these settings:
   - Host: `localhost`
   - Port: `1025`
   - Username: (leave empty)
   - Password: (leave empty)
   - Use TLS: `false`

4. View emails at: http://localhost:8025

## Backend Configuration

Make sure your FastAPI backend loads environment variables from `.env` file.

If using `python-dotenv`, add this to `backend/main.py`:

```python
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()

# Now environment variables are available via os.getenv()
```

Or if using `uvicorn` with `python-dotenv`:

```bash
pip install python-dotenv
```

Then in your backend code, access variables via:
```python
import os
smtp_host = os.environ.get('SMTP_HOST')
```

## Testing

After setting up, test the email functionality:

1. Start your backend server
2. Go to Settings → Index → Email Index Script
3. Enter an email address
4. Click "Send Email"

If configured correctly, you should see a success message. If using Mailtrap, check your Mailtrap inbox to see the captured email.

## Troubleshooting

### "SMTP not configured" error
- Make sure environment variables are set
- Restart your backend server after setting variables
- Check that `.env` file is in the correct location (backend directory)

### "SMTP server error"
- Verify SMTP credentials are correct
- Check that SMTP server is accessible
- For Gmail: Make sure you're using an app password, not your regular password
- For Mailtrap: Check that your inbox is active

### Variables not persisting
- Use `.env` file for permanent setup
- Or set variables in your system environment (Windows: System Properties → Environment Variables)

