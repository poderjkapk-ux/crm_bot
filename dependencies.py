# dependencies.py
import secrets
from typing import Generator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from models import async_session_maker

security = HTTPBasic()

def check_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверяет учетные данные администратора."""
    is_user_ok = secrets.compare_digest(credentials.username, "admin")
    is_pass_ok = secrets.compare_digest(credentials.password, "admin13369")
    if not (is_user_ok and is_pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неправильный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

async def get_db_session() -> Generator[AsyncSession, None, None]:
    """Создает и предоставляет сессию базы данных для эндпоинта."""
    async with async_session_maker() as session:
        yield session
