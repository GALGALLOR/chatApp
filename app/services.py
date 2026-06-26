from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from . import models, schemas


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_message(db: Session, data: schemas.MessageCreate) -> tuple[models.Message, models.Notification]:
    message = models.Message(
        sender_id=data.sender_id,
        receiver_id=data.receiver_id,
        content=data.content,
        status=models.MessageStatus.SENT.value,
    )
    try:
        db.add(message)
        db.flush()
        notification = models.Notification(
            user_id=data.receiver_id,
            message_id=message.id,
            title=f"New message from user {data.sender_id}",
            body=data.content,
        )
        db.add(notification)
        db.commit()
        db.refresh(message)
        db.refresh(notification)
        return message, notification
    except Exception:
        db.rollback()
        raise


def get_messages_for_user(db: Session, user_id: int) -> list[models.Message]:
    statement = (
        select(models.Message)
        .where(or_(models.Message.sender_id == user_id, models.Message.receiver_id == user_id))
        .order_by(models.Message.created_at.desc(), models.Message.id.desc())
    )
    return list(db.scalars(statement))


def get_notifications_for_user(db: Session, user_id: int) -> list[models.Notification]:
    statement = (
        select(models.Notification)
        .where(models.Notification.user_id == user_id)
        .order_by(models.Notification.created_at.desc(), models.Notification.id.desc())
    )
    return list(db.scalars(statement))


def mark_notification_read(db: Session, notification_id: int) -> models.Notification:
    notification = db.get(models.Notification, notification_id)
    if notification is None:
        raise ServiceError(404, "Notification not found")
    if not notification.is_read:
        notification.is_read = True
        db.commit()
        db.refresh(notification)
    return notification


def acknowledge_delivery(
    db: Session, message_id: int, connected_user_id: int
) -> tuple[models.Message, bool]:
    message = db.get(models.Message, message_id)
    if message is None:
        raise ServiceError(404, "Message not found")
    if message.receiver_id != connected_user_id:
        raise ServiceError(403, "Only the receiver can acknowledge delivery")

    # A conditional update ensures two receiver tabs cannot both win the same
    # SENT -> DELIVERED transition and generate duplicate sender receipts.
    result = db.execute(
        update(models.Message)
        .where(
            models.Message.id == message_id,
            models.Message.receiver_id == connected_user_id,
            models.Message.status == models.MessageStatus.SENT.value,
        )
        .values(status=models.MessageStatus.DELIVERED.value, delivered_at=models.utc_now())
    )
    transitioned = result.rowcount == 1
    db.commit()
    db.refresh(message)
    return message, transitioned


def mark_message_read(
    db: Session, message_id: int, user_id: int
) -> tuple[models.Message, bool]:
    message = db.get(models.Message, message_id)
    if message is None:
        raise ServiceError(404, "Message not found")
    if message.receiver_id != user_id:
        raise ServiceError(403, "Only the receiver can mark this message as read")

    now = models.utc_now()
    result = db.execute(
        update(models.Message)
        .where(
            models.Message.id == message_id,
            models.Message.receiver_id == user_id,
            models.Message.status != models.MessageStatus.READ.value,
        )
        .values(
            status=models.MessageStatus.READ.value,
            # Reading proves delivery even if the WebSocket acknowledgment was missed.
            delivered_at=func.coalesce(models.Message.delivered_at, now),
            read_at=now,
        )
    )
    transitioned = result.rowcount == 1
    db.commit()
    db.refresh(message)
    return message, transitioned
