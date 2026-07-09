import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password
from app.scheduler import scheduler_loop
from app.routers import auth, devices, monitoring, users, wan
from app.wan_monitor import wan_loop
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("netmonitor")


def seed_admin_user():
    db = SessionLocal()
    try:
        exists = db.query(User).filter(User.username == settings.admin_user).first()
        if not exists:
            user = User(
                username=settings.admin_user,
                password_hash=hash_password(settings.admin_password),
            )
            db.add(user)
            db.commit()
            logger.info("Usuário admin '%s' criado.", settings.admin_user)
    finally:
        db.close()


def run_migrations():
    """Migrações leves para bancos criados na V1."""
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'admin'"
        ))
        conn.execute(text(
            "ALTER TABLE speedtest_results ADD COLUMN IF NOT EXISTS wan_ip VARCHAR(64)"
        ))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_migrations()
    seed_admin_user()
    task = asyncio.create_task(scheduler_loop())
    wan_task = asyncio.create_task(wan_loop())
    logger.info("Aplicação iniciada.")
    yield
    task.cancel()
    wan_task.cancel()


app = FastAPI(title="VMN Pulse", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(monitoring.router)
app.include_router(users.router)
app.include_router(wan.router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/internet.html")
def internet_page():
    return FileResponse("static/internet.html")


@app.get("/correlation.html")
def correlation_page():
    return FileResponse("static/correlation.html")


@app.get("/device.html")
def device_page():
    return FileResponse("static/device.html")


@app.get("/login.html")
def login_page():
    return FileResponse("static/login.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}
