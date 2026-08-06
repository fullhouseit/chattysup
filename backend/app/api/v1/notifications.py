"""Email notification status, per-agent preferences and a test send."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...core.deps import CurrentUser, DbSession, get_current_admin, get_current_user
from ...schemas import NotificationPreferences
from ...services import mailer, notifications, settings_service

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/status")
async def status(db: DbSession, user: CurrentUser) -> dict:
    """Whether mail can be sent at all, and why not when it cannot."""
    configured = mailer.is_configured()
    enabled = bool(await settings_service.get(db, notifications.SETTING_KEY, False))

    reason = None
    if not configured:
        reason = (
            "SMTP is not configured. Set SMTP_HOST and SMTP_FROM_EMAIL in the "
            "environment, then restart."
        )
    elif not enabled:
        reason = "Email notifications are switched off for this installation."

    body: dict = {
        "smtp_configured": configured,
        "enabled": enabled,
        "operational": configured and enabled,
        "reason": reason,
        "my_email": user.email,
        "my_notifications_enabled": user.email_notifications,
    }
    if user.role == "admin":
        body["smtp"] = mailer.describe()
    return body


@router.get("/preferences")
async def get_preferences(user: CurrentUser) -> dict:
    return {
        "email_notifications": user.email_notifications,
        "preferences": notifications.preferences_for(user),
        "defaults": notifications.DEFAULT_PREFERENCES,
    }


@router.patch("/preferences")
async def update_preferences(
    payload: NotificationPreferences, db: DbSession, user: CurrentUser
) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if "email_notifications" in data:
        user.email_notifications = bool(data.pop("email_notifications"))

    if data:
        merged = {**notifications.preferences_for(user), **data}
        # Store only known keys so a stale client cannot grow the blob.
        user.notification_settings = {
            key: merged[key] for key in notifications.DEFAULT_PREFERENCES if key in merged
        }
    await db.flush()
    return {
        "email_notifications": user.email_notifications,
        "preferences": notifications.preferences_for(user),
        "defaults": notifications.DEFAULT_PREFERENCES,
    }


@router.post("/test", dependencies=[Depends(get_current_admin)])
async def send_test(user: CurrentUser) -> dict:
    """Send a test email to the caller's own address."""
    if not user.email:
        raise HTTPException(status_code=422, detail="Your account has no email address")
    try:
        await notifications.send_test_email(user)
    except mailer.MailError as exc:
        # A misconfigured mail server is an operator error, not a server fault.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "sent", "to": user.email}
