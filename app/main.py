from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import Base, SessionLocal, engine, get_db
from .websocket_manager import manager


BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Notification & Messaging MVP", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def raise_http_error(error: services.ServiceError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail)


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/api/messages", response_model=schemas.CreateMessageResponse, status_code=201)
async def send_message(data: schemas.MessageCreate, db: Session = Depends(get_db)):
    message, notification = services.create_message(db, data)
    event = {
        "type": "NEW_MESSAGE_NOTIFICATION",
        "message": jsonable_encoder(schemas.MessageResponse.model_validate(message)),
        "notification": jsonable_encoder(schemas.NotificationResponse.model_validate(notification)),
    }
    delivered_socket_count = await manager.send_to_user(message.receiver_id, event)
    return {
        "message": message,
        "notification": notification,
        "receiver_online": delivered_socket_count > 0,
    }


@app.get("/api/messages/{user_id}", response_model=list[schemas.MessageResponse])
def list_messages(user_id: int, db: Session = Depends(get_db)):
    if user_id <= 0:
        raise HTTPException(status_code=422, detail="user_id must be positive")
    return services.get_messages_for_user(db, user_id)


@app.get("/api/notifications/{user_id}", response_model=list[schemas.NotificationResponse])
def list_notifications(user_id: int, db: Session = Depends(get_db)):
    if user_id <= 0:
        raise HTTPException(status_code=422, detail="user_id must be positive")
    return services.get_notifications_for_user(db, user_id)


@app.patch("/api/notifications/{notification_id}/read", response_model=schemas.NotificationResponse)
def read_notification(notification_id: int, db: Session = Depends(get_db)):
    if notification_id <= 0:
        raise HTTPException(status_code=422, detail="notification_id must be positive")
    try:
        return services.mark_notification_read(db, notification_id)
    except services.ServiceError as error:
        raise_http_error(error)


@app.patch("/api/messages/{message_id}/read", response_model=schemas.MessageResponse)
async def read_message(
    message_id: int,
    user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    if message_id <= 0:
        raise HTTPException(status_code=422, detail="message_id must be positive")
    try:
        message, transitioned = services.mark_message_read(db, message_id, user_id)
    except services.ServiceError as error:
        raise_http_error(error)

    if transitioned:
        await manager.send_to_user(
            message.sender_id,
            {"type": "MESSAGE_READ", "message_id": message.id, "receiver_id": message.receiver_id},
        )
    return message


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int):
    if user_id <= 0:
        await websocket.close(code=1008, reason="user_id must be positive")
        return

    await manager.connect(user_id, websocket)
    await websocket.send_json({"type": "CONNECTED", "user_id": user_id})
    try:
        while True:
            raw_data = await websocket.receive_json()
            try:
                acknowledgment = schemas.DeliveryAcknowledgment.model_validate(raw_data)
                if acknowledgment.type != "DELIVERED":
                    await websocket.send_json({"type": "ERROR", "detail": "Unsupported event type"})
                    continue

                # The path user ID is the identity used to authorize the acknowledgment.
                with SessionLocal() as db:
                    message, transitioned = services.acknowledge_delivery(
                        db, acknowledgment.message_id, user_id
                    )
                await websocket.send_json(
                    {
                        "type": "DELIVERY_ACKNOWLEDGED",
                        "message_id": message.id,
                        "status": message.status,
                    }
                )
                if transitioned:
                    await manager.send_to_user(
                        message.sender_id,
                        {
                            "type": "MESSAGE_DELIVERED",
                            "message_id": message.id,
                            "receiver_id": message.receiver_id,
                        },
                    )
            except ValidationError as error:
                await websocket.send_json(
                    {"type": "ERROR", "detail": "Invalid acknowledgment", "errors": error.errors()}
                )
            except services.ServiceError as error:
                await websocket.send_json({"type": "ERROR", "detail": error.detail})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await manager.disconnect(user_id, websocket)

