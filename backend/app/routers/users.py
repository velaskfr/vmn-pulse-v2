from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserOut, UserPasswordReset
from app.security import require_admin, hash_password

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    if payload.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="Papel inválido (use admin ou viewer)")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Já existe um usuário com esse nome")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/password", response_model=UserOut)
def reset_password(user_id: int, payload: UserPasswordReset, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir o seu próprio usuário")
    admins = db.query(User).filter(User.role == "admin").count()
    if user.role == "admin" and admins <= 1:
        raise HTTPException(status_code=400, detail="Não é possível excluir o último administrador")
    db.delete(user)
    db.commit()
    return None
