from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from sqlalchemy import func
import random
import os

from .database import engine, Base, get_db, SessionLocal
from .models import (
    User, Account, Transaction, Card,
    UserRole, AccountStatus, TransactionType, TransactionStatus,
    CardStatus, CardType
)
from .auth import (
    get_password_hash, authenticate_user, create_access_token,
    get_current_user, require_user, require_admin, ACCESS_TOKEN_EXPIRE_MINUTES
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Lancrest Credit Union Bank - Educational Demo")
templates = Jinja2Templates(directory="templates")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


def generate_account_number():
    return f"LC{random.randint(10000000, 99999999)}"


def generate_card_number():
    return f"4{random.randint(100,999)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)}"


def generate_cvv():
    return str(random.randint(100, 999))


def generate_expiry():
    year = datetime.now().year + 3
    month = random.randint(1, 12)
    return f"{month:02d}/{str(year)[2:]}"


def seed_data():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "admin@lancrest.demo").first()
        if admin:
            return

        # Admin
        admin = User(
            email="admin@lancrest.demo",
            username="admin",
            full_name="System Administrator",
            password_hash=get_password_hash("admin123"),
            role=UserRole.admin,
        )
        db.add(admin)
        db.flush()
        db.add(Account(user_id=admin.id, account_number=generate_account_number(), balance=0.0))

        # Demo users
        demos = [
            ("sarah.johnson@lancrest.demo", "sarah", "Sarah Johnson", 4250.75),
            ("michael.chen@lancrest.demo", "michael", "Michael Chen", 1875.00),
            ("aisha.okonkwo@lancrest.demo", "aisha", "Aisha Okonkwo", 6320.40),
        ]
        for email, username, full_name, balance in demos:
            user = User(
                email=email,
                username=username,
                full_name=full_name,
                password_hash=get_password_hash("password123"),
                role=UserRole.user,
            )
            db.add(user)
            db.flush()
            account = Account(
                user_id=user.id,
                account_number=generate_account_number(),
                balance=balance,
            )
            db.add(account)
            db.flush()
            # Initial deposit
            db.add(Transaction(
                account_id=account.id,
                type=TransactionType.admin_credit,
                amount=balance,
                description="Initial account funding",
                status=TransactionStatus.completed,
            ))

        db.commit()
        print("✅ Lancrest seed data created")
        print("   Admin → admin@lancrest.demo / admin123")
        print("   Users → sarah / michael / aisha  @lancrest.demo / password123")
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    seed_data()


# ====================== PUBLIC / AUTH ======================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request, "user": None})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = await get_current_user(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid email or password"}, status_code=400)
    token = create_access_token(data={"sub": user.email}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
async def register(
    request: Request,
    email: str = Form(...),
    username: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.email == email).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Email already registered"}, status_code=400)
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username taken"}, status_code=400)
    if len(password) < 6:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Password must be at least 6 characters"}, status_code=400)

    user = User(
        email=email.strip().lower(),
        username=username.strip(),
        full_name=full_name.strip(),
        password_hash=get_password_hash(password),
        role=UserRole.user,
    )
    db.add(user)
    db.flush()
    account = Account(user_id=user.id, account_number=generate_account_number(), balance=0.0)
    db.add(account)
    db.commit()

    token = create_access_token(data={"sub": user.email})
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {token}", httponly=True, max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie("access_token")
    return response


# ====================== USER DASHBOARD ======================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.user_id == user.id).first()
    if account.status == AccountStatus.frozen and user.role != UserRole.admin:
        return templates.TemplateResponse("frozen.html", {"request": request, "user": user})

    # Running balance history
    all_tx = db.query(Transaction).filter(Transaction.account_id == account.id).order_by(Transaction.created_at.asc()).all()
    history = []
    running = 0.0
    for tx in all_tx:
        if tx.type in (TransactionType.deposit, TransactionType.transfer_in, TransactionType.admin_credit):
            running += tx.amount
        else:
            running -= tx.amount
        history.append({"tx": tx, "running_balance": running})
    history.reverse()

    cards = db.query(Card).filter(Card.user_id == user.id).all()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "account": account,
        "history": history[:30],
        "cards": cards,
    })


# ====================== TRANSFER ======================

@app.get("/transfer", response_class=HTMLResponse)
async def transfer_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.user_id == user.id).first()
    return templates.TemplateResponse("transfer.html", {
        "request": request, "user": user, "account": account, "error": None, "success": None
    })


@app.post("/transfer")
async def transfer(
    request: Request,
    recipient: str = Form(...),
    amount: float = Form(...),
    description: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.user_id == user.id).first()
    if account.status == AccountStatus.frozen:
        return templates.TemplateResponse("transfer.html", {
            "request": request, "user": user, "account": account,
            "error": "Your account is frozen", "success": None
        }, status_code=400)

    if amount <= 0:
        return templates.TemplateResponse("transfer.html", {
            "request": request, "user": user, "account": account,
            "error": "Amount must be greater than zero", "success": None
        }, status_code=400)

    if amount > account.balance:
        return templates.TemplateResponse("transfer.html", {
            "request": request, "user": user, "account": account,
            "error": "Insufficient funds", "success": None
        }, status_code=400)

    # Find recipient by username or account number
    recipient_user = db.query(User).filter(User.username == recipient.strip()).first()
    recipient_account = None
    if recipient_user:
        recipient_account = db.query(Account).filter(Account.user_id == recipient_user.id).first()
    else:
        recipient_account = db.query(Account).filter(Account.account_number == recipient.strip()).first()

    if not recipient_account:
        return templates.TemplateResponse("transfer.html", {
            "request": request, "user": user, "account": account,
            "error": "Recipient not found", "success": None
        }, status_code=400)

    if recipient_account.id == account.id:
        return templates.TemplateResponse("transfer.html", {
            "request": request, "user": user, "account": account,
            "error": "Cannot transfer to yourself", "success": None
        }, status_code=400)

    # Execute transfer
    account.balance -= amount
    recipient_account.balance += amount

    db.add(Transaction(
        account_id=account.id,
        type=TransactionType.transfer_out,
        amount=amount,
        description=description or f"Transfer to {recipient}",
        related_account_id=recipient_account.id,
    ))
    db.add(Transaction(
        account_id=recipient_account.id,
        type=TransactionType.transfer_in,
        amount=amount,
        description=description or f"Transfer from {user.username}",
        related_account_id=account.id,
    ))
    db.commit()

    return templates.TemplateResponse("transfer.html", {
        "request": request, "user": user, "account": account,
        "error": None, "success": f"Successfully transferred ${amount:.2f}"
    })


# ====================== BILL PAY ======================

@app.get("/bills", response_class=HTMLResponse)
async def bills_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.user_id == user.id).first()
    return templates.TemplateResponse("bills.html", {
        "request": request, "user": user, "account": account, "error": None, "success": None
    })


@app.post("/bills")
async def pay_bill(
    request: Request,
    provider: str = Form(...),
    account_ref: str = Form(...),
    amount: float = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.user_id == user.id).first()
    if account.status == AccountStatus.frozen:
        return templates.TemplateResponse("bills.html", {
            "request": request, "user": user, "account": account,
            "error": "Account is frozen", "success": None
        }, status_code=400)

    if amount <= 0 or amount > account.balance:
        return templates.TemplateResponse("bills.html", {
            "request": request, "user": user, "account": account,
            "error": "Invalid amount or insufficient funds", "success": None
        }, status_code=400)

    account.balance -= amount
    db.add(Transaction(
        account_id=account.id,
        type=TransactionType.bill_pay,
        amount=amount,
        description=f"{provider} – Ref: {account_ref}",
        status=TransactionStatus.completed,
    ))
    db.commit()

    return templates.TemplateResponse("bills.html", {
        "request": request, "user": user, "account": account,
        "error": None,
        "success": f"Paid ${amount:.2f} to {provider}. Reference: {account_ref}"
    })


# ====================== CARDS ======================

@app.get("/cards", response_class=HTMLResponse)
async def cards_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    cards = db.query(Card).filter(Card.user_id == user.id).all()
    return templates.TemplateResponse("cards.html", {
        "request": request, "user": user, "cards": cards, "error": None, "success": None
    })


@app.post("/cards/request-virtual")
async def request_virtual_card(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    existing = db.query(Card).filter(Card.user_id == user.id, Card.card_type == CardType.virtual).first()
    if existing and existing.status in (CardStatus.active, CardStatus.pending, CardStatus.frozen):
        cards = db.query(Card).filter(Card.user_id == user.id).all()
        return templates.TemplateResponse("cards.html", {
            "request": request, "user": user, "cards": cards,
            "error": "You already have a virtual card", "success": None
        })

    card = Card(
        user_id=user.id,
        card_type=CardType.virtual,
        card_number=generate_card_number(),
        cvv=generate_cvv(),
        expiry=generate_expiry(),
        status=CardStatus.active,  # Instant for demo
    )
    db.add(card)
    db.commit()

    cards = db.query(Card).filter(Card.user_id == user.id).all()
    return templates.TemplateResponse("cards.html", {
        "request": request, "user": user, "cards": cards,
        "error": None, "success": "Virtual card created successfully"
    })


@app.post("/cards/freeze/{card_id}")
async def freeze_card(card_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    card = db.query(Card).filter(Card.id == card_id, Card.user_id == user.id).first()
    if card:
        card.status = CardStatus.frozen if card.status == CardStatus.active else CardStatus.active
        db.commit()
    return RedirectResponse("/cards", status_code=303)


# ====================== ADMIN ======================

@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_users = db.query(User).filter(User.role == UserRole.user).count()
    total_balance = db.query(func.sum(Account.balance)).scalar() or 0.0
    total_tx = db.query(Transaction).count()
    users = db.query(User).order_by(User.created_at.desc()).all()
    accounts = {a.user_id: a for a in db.query(Account).all()}
    pending_cards = db.query(Card).filter(Card.status == CardStatus.pending).all()

    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": admin,
        "total_users": total_users,
        "total_balance": total_balance,
        "total_tx": total_tx,
        "users": users,
        "accounts": accounts,
        "pending_cards": pending_cards,
        "success": None,
        "error": None,
    })


@app.post("/admin/adjust-balance")
async def admin_adjust(
    request: Request,
    user_id: int = Form(...),
    amount: float = Form(...),
    action: str = Form(...),          # credit or debit
    description: str = Form("Admin adjustment"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    account = db.query(Account).filter(Account.user_id == user_id).first()
    target = db.query(User).filter(User.id == user_id).first()
    if not account or not target:
        raise HTTPException(404, "User not found")

    if amount <= 0:
        return RedirectResponse("/admin", status_code=303)

    if action == "credit":
        account.balance += amount
        tx_type = TransactionType.admin_credit
        desc = description or "Admin Credit / Deposit"
    else:
        if amount > account.balance:
            amount = account.balance
        account.balance -= amount
        tx_type = TransactionType.admin_debit
        desc = description or "Admin Debit"

    db.add(Transaction(
        account_id=account.id,
        type=tx_type,
        amount=amount,
        description=desc,
        status=TransactionStatus.completed,
    ))
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/toggle-status/{user_id}")
async def toggle_account_status(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.user_id == user_id).first()
    if account:
        account.status = AccountStatus.frozen if account.status == AccountStatus.active else AccountStatus.active
        db.commit()
    return RedirectResponse("/admin", status_code=303)


@app.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def admin_view_user(user_id: int, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(404)
    account = db.query(Account).filter(Account.user_id == user_id).first()
    all_tx = db.query(Transaction).filter(Transaction.account_id == account.id).order_by(Transaction.created_at.asc()).all()
    history = []
    running = 0.0
    for tx in all_tx:
        if tx.type in (TransactionType.deposit, TransactionType.transfer_in, TransactionType.admin_credit):
            running += tx.amount
        else:
            running -= tx.amount
        history.append({"tx": tx, "running_balance": running})
    history.reverse()

    return templates.TemplateResponse("admin_user.html", {
        "request": request, "user": admin, "target": target, "account": account, "history": history
    })
