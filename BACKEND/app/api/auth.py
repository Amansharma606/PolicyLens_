from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.db_models import User
from app.models.schemas import UserLoginRequest, AuthResponse, UserResponse
from app.core.security import verify_password, create_access_token, get_current_user_required

router = APIRouter()

@router.post("/auth/login", response_model=AuthResponse, tags=["Authentication"])
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates user and returns JWT Bearer token.
    """
    email_clean = request.email.strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please verify your credentials."
        )

    user_profile = UserResponse(
        email=user.email,
        name=user.name,
        role=user.role,
        department=user.department,
        avatar=user.avatar
    )

    token_data = {
        "sub": user.email,
        "name": user.name,
        "role": user.role,
        "department": user.department,
        "user_id": user.id
    }
    access_token = create_access_token(token_data)

    return AuthResponse(
        user=user_profile,
        token=access_token,
        mode="backend"
    )

@router.post("/auth/logout", tags=["Authentication"])
def logout():
    return {"message": "Logged out successfully"}

@router.get("/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_profile(user_payload: dict = Depends(get_current_user_required), db: Session = Depends(get_db)):
    email = user_payload.get("sub")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        email=user.email,
        name=user.name,
        role=user.role,
        department=user.department,
        avatar=user.avatar
    )
