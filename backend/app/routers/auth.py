"""
Authentication router for S2PNexus.

Handles user authentication, registration, and token management.
"""

from datetime import timedelta
from typing import Annotated

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    get_password_hash,
    decode_token,
    get_act_as_claims,
)
from app.crud.user import get_user_by_email, get_user_by_id, create_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.act_as import ActAsStatusResponse, ActAsUserSummary
from app.schemas.auth import (
    Token,
    TokenRefresh,
    UserRegister,
    UserLogin,
    UserResponse,
    MeResponse,
    MessageResponse,
)
from app.schemas.user import UserCreate, UserUpdate
from app.utils.dependencies import get_current_user, get_current_active_user

_bearer = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth", tags=["Authentication"])
settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new user",
    description="Create a new user account",
)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Register a new user.

    Args:
        user_data: User registration data
        db: Database session

    Returns:
        UserResponse: Created user information

    Raises:
        HTTPException: If email already registered
    """
    # Check if user exists
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user_create = UserCreate(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        role=user_data.role,
        is_active=True,
        is_superuser=False,
    )
    user = await create_user(db, user_create)

    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=Token,
    summary="User login",
    description="Authenticate user and return access/refresh tokens",
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Authenticate user and return tokens.

    Args:
        form_data: OAuth2 password request form
        db: Database session

    Returns:
        Token: Access and refresh tokens

    Raises:
        HTTPException: If authentication fails
    """
    user = await get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id,
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/refresh",
    response_model=Token,
    summary="Refresh access token",
    description="Get new access token using refresh token",
)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db),
) -> Token:
    """
    Refresh access token.

    Args:
        token_data: Refresh token data
        db: Database session

    Returns:
        Token: New access and refresh tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    payload = decode_token(token_data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id,
        expires_delta=access_token_expires,
    )
    new_refresh_token = create_refresh_token(subject=user.id)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="User logout",
    description="Logout user (client-side token removal)",
)
async def logout() -> MessageResponse:
    """
    Logout user.

    Note: With JWT, logout is primarily client-side.
    Server-side token blacklisting can be implemented with Redis.

    Returns:
        MessageResponse: Success message
    """
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user",
    description="Get authenticated user profile, plus act-as (impersonation) status",
)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_active_user)],
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    """
    Get current authenticated user profile.

    If the request's token is an Act as User impersonation token,
    `current_user` already resolves to the impersonated TARGET user (its
    `sub` claim) -- everything downstream of get_current_active_user works
    unchanged. `act_as` on the response additionally surfaces who the real
    admin is, so the frontend can render/restore the "Acting as" banner on a
    page refresh without a separate call.
    """
    act_as = ActAsStatusResponse(is_impersonating=False)
    if credentials:
        claims = get_act_as_claims(credentials.credentials)
        if claims:
            admin = await get_user_by_id(db, UUID(claims.admin_user_id))
            if admin is not None:
                act_as = ActAsStatusResponse(
                    is_impersonating=True,
                    session_id=claims.session_id,
                    admin_user=ActAsUserSummary(
                        id=admin.id, full_name=admin.full_name, email=admin.email, role=admin.role.value
                    ),
                )
    return MeResponse(**UserResponse.model_validate(current_user).model_dump(), act_as=act_as)


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user",
    description="Update authenticated user profile",
)
async def update_current_user(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Update current user profile.

    Args:
        user_update: User update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        UserResponse: Updated user profile
    """
    from app.crud.user import update_user

    updated_user = await update_user(db, current_user.id, user_update)
    return UserResponse.model_validate(updated_user)


@router.post(
    "/change-password",
    response_model=MessageResponse,
    summary="Change password",
    description="Change user password",
)
async def change_password(
    current_password: str,
    new_password: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Change user password.

    Args:
        current_password: Current password
        new_password: New password
        current_user: Current authenticated user
        db: Database session

    Returns:
        MessageResponse: Success message

    Raises:
        HTTPException: If current password is incorrect
    """
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(new_password) < settings.PASSWORD_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters",
        )

    from app.crud.user import update_user
    from app.schemas.user import UserUpdate

    await update_user(
        db,
        current_user.id,
        UserUpdate(hashed_password=get_password_hash(new_password)),
    )

    return MessageResponse(message="Password changed successfully")