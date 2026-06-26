from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import MessageStatus


class MessageCreate(BaseModel):
    sender_id: int = Field(gt=0)
    receiver_id: int = Field(gt=0)
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("content must not be empty")
        return value

    @model_validator(mode="after")
    def users_must_be_different(self) -> "MessageCreate":
        if self.sender_id == self.receiver_id:
            raise ValueError("sender_id and receiver_id must be different")
        return self


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    receiver_id: int
    content: str
    status: MessageStatus
    created_at: datetime
    delivered_at: datetime | None
    read_at: datetime | None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    message_id: int
    title: str
    body: str
    is_read: bool
    created_at: datetime


class CreateMessageResponse(BaseModel):
    message: MessageResponse
    notification: NotificationResponse
    receiver_online: bool


class DeliveryAcknowledgment(BaseModel):
    type: str
    message_id: int = Field(gt=0)

