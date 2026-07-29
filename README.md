# Lancrest Credit Union Bank – Educational MVP

A modern educational banking simulation with Admin and User roles.

**This is a demo only. Not a real bank. No real money.**

## Features

### User
- Account balance & account number
- Transaction history with running balance
- Transfer to other members
- Pay Bills (Electricity, Water, Internet, TV, Gas)
- Request Virtual Card + Freeze/Unfreeze

### Admin
- Dashboard stats (users, total deposits, transactions)
- View all members
- Freeze / Activate accounts
- Manual Credit & Debit with description
- View any member’s full history

## Demo Accounts

| Role  | Email                          | Password    |
|-------|--------------------------------|-------------|
| Admin | admin@lancrest.demo            | admin123    |
| User  | sarah.johnson@lancrest.demo    | password123 |
| User  | michael.chen@lancrest.demo     | password123 |
| User  | aisha.okonkwo@lancrest.demo    | password123 |

## Run Locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000

## Deploy on Render

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Root Directory: leave empty
