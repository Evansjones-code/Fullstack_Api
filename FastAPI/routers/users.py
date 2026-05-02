from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    File,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from PIL import UnidentifiedImageError
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

import models
from auth import (
    CurrentUser,
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from config import settings
from database import get_db
from email_utils import send_password_reset_email
from image_utils import (
    delete_profile_image,
    process_profile_image,
    upload_profile_image,
)
from schemas import (
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserPrivate,
    UserPublic,
)

router = APIRouter()

@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == user.email.lower())
    )
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        username=user.username,
        email=user.email.lower(),
        password_hash=hash_password(user.password),
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == form_data.username.lower())
    )
    user = result.scalars().first()

    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return Token(access_token=token, token_type="bearer")

@router.get("/me", response_model=UserPrivate)
async def get_current_user(current_user: CurrentUser):
    return current_user

# --- ACCOUNT SETTINGS UPDATES ---

@router.put("/{user_id}", response_model=UserPrivate)
async def update_user(
    user_id: int,
    user_data: UserCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile")
    
    current_user.username = user_data.username
    current_user.email = user_data.email.lower()
    
    await db.commit()
    await db.refresh(current_user)
    return current_user

@router.post("/{user_id}/profile-pic", response_model=UserPrivate)
async def upload_profile_pic_by_id(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    picture: UploadFile = File(...), # Matches 'picture' key in account.html
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Calls the local patch logic
    return await update_profile_image(picture, current_user, db)

@router.put("/{user_id}/password")
async def change_password(
    user_id: int,
    passwords: dict,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not verify_password(passwords.get("current_password"), current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    current_user.password_hash = hash_password(passwords.get("new_password"))
    await db.commit()
    return {"message": "Password updated successfully"}

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if current_user.image_file:
        await delete_profile_image(current_user.image_file)
        
    await db.delete(current_user)
    await db.commit()
    return None

# --- CORE IMAGE LOGIC ---

@router.patch("/me/image", response_model=UserPrivate)
async def update_profile_image(
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    try:
        content = await file.read()
        image_data, filename = await run_in_threadpool(process_profile_image, content)
        
        # Upload to S3/Storage
        await upload_profile_image(image_data, filename)
        
        # Cleanup old image
        if current_user.image_file and current_user.image_file != "default.jpg":
            await delete_profile_image(current_user.image_file)
            
        current_user.image_file = filename
        await db.commit()
        await db.refresh(current_user)
        return current_user

    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Invalid image format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- PASSWORD RECOVERY ---

@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(models.User).where(func.lower(models.User.email) == request_data.email.lower())
    )
    user = result.scalars().first()

    if user:
        token = generate_reset_token()
        reset_token = models.PasswordResetToken(
            user_id=user.id,
            token_hash=hash_reset_token(token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expire_minutes)
        )
        db.add(reset_token)
        await db.commit()
        background_tasks.add_task(
            send_password_reset_email, 
            to_email=user.email, 
            username=user.username, 
            token=token
        )

    return {"message": "Reset instructions sent if account exists."}

@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    user = result.scalars().first()
    if user:
        return user
    raise HTTPException(status_code=404, detail="User not found")
