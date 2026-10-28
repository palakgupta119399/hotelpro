# HotelPro — Full-stack hotel booking website

This project is a working Flask + SQLite web application, not just a static mock-up.

## Features
- Real server-side signup/login with hashed passwords and session cookies
- SQLite database for users, rooms and reservations (data persists after restart)
- Date validation, guest capacity checks and overlapping booking checks
- My Bookings page and cancellation
- Admin dashboard to view bookings/users, add rooms, and disable/enable room listings
- Responsive pages for mobile and desktop

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open http://127.0.0.1:5000

## Create an administrator account
Set these environment variables before starting the app. The admin is created on first startup if it does not already exist.

Windows PowerShell:
```powershell
$env:ADMIN_EMAIL="your-admin@example.com"
$env:ADMIN_PASSWORD="use-a-strong-password-here"
$env:SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

macOS/Linux:
```bash
export ADMIN_EMAIL="your-admin@example.com"
export ADMIN_PASSWORD="use-a-strong-password-here"
export SECRET_KEY="replace-with-a-long-random-secret"
python app.py
```

Do not use real customer data until deployed over HTTPS with production configuration. For production, set a strong random SECRET_KEY, turn off debug mode, configure HTTPS/security headers, backups, rate limiting, CSRF protection, and a production database/hosting service. This project does not process payments or connect to a real hotel's inventory.
