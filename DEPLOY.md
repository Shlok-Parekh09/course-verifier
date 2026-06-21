# Deployment Guide – Course Verifier

## Quick Start (Local / Bare Metal)

```bash
# 1. Clone / copy the project
cd course-verifier

# 2. Fill in SMTP credentials inside .env
nano .env
#    SMTP_USER=your@gmail.com
#    SMTP_PASS=your-app-password
#    SMTP_TO=yugshah197@gmail.com
#    SEND_EMAIL_ON_COMPLETE=true

# 3. Install deps
pip install -r requirements.txt

# 4. Run verifier for pages 602-1890 (fully automated, no prompts)
python run_verifier_pages.py link_compile.pdf --pages 602 1890
```

## Flags for `run_verifier_pages.py`

| Flag | Description |
|------|-------------|
| `--pages START END` | Process PDF pages START to END (default 602-1890). |
| `--resume` / `-r` | Resume from existing checkpoint JSON. |
| `--all` | Process every page in the PDF. |
| `--no-email` | Skip the e-mail report step. |

## Docker (External Server)

```bash
# Build image
docker compose build

# Run verifier + dashboard
docker compose up -d

# View logs
docker compose logs -f verifier

# Stop
docker compose down
```

## Windows (Existing Workflow)

```powershell
$Env:VERIFIER_NO_FORCE_EXIT="true"
python run_verifier_pages.py link_compile.pdf --pages 602 1890
```

## E-mail Setup (Gmail App Password)

1. Go to https://myaccount.google.com/apppasswords
2. Generate a 16-character app password.
3. Paste it into `.env`:
   ```
   SMTP_USER=your.email@gmail.com
   SMTP_PASS=xxxx xxxx xxxx xxxx
   SMTP_FROM=your.email@gmail.com
   SMTP_TO=yugshah197@gmail.com
   SEND_EMAIL_ON_COMPLETE=true
   ```

## Architecture

- **`run_verifier_pages.py`** – Entry point. No interactive prompts. Maps page numbers to course indices, drives the verifier, triggers e-mail.
- **`autonomous_course_verifier.py`** – Core engine (modified to avoid `os._exit` when `VERIFIER_NO_FORCE_EXIT=true`).
- **`email_sender.py`** – Lightweight SMTP wrapper.
- **`dashboard.py`** – Flask dashboard (auto-merges verifier JSON on startup).
- **`docker-compose.yml`** – Orchestrates headless Chrome + verifier + dashboard.
