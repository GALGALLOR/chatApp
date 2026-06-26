# FastAPI Notification & Messaging MVP

A small in-app messaging demo. The backend stores each message and notification in SQLite, pushes new-message events to connected receivers over WebSockets, accepts automatic delivery acknowledgments, and sends delivery/read receipts back to connected senders.

This is intentionally a local MVP: user identity is a positive numeric ID, and there is no authentication or SMS integration.

## Project tree

```text
.
├── .gitignore                  Local Python and SQLite artifacts
├── app/
│   ├── __init__.py             Python package marker
│   ├── database.py             SQLite engine and database sessions
│   ├── main.py                 FastAPI routes, startup, and WebSocket handler
│   ├── models.py               SQLAlchemy message and notification tables
│   ├── schemas.py              Request and response validation
│   ├── services.py             Database business logic and status transitions
│   ├── websocket_manager.py    Active WebSocket connections by user
│   └── static/
│       └── index.html          Browser UI and WebSocket client
├── tests/
│   ├── conftest.py             Isolated in-memory test database
│   ├── test_api.py             REST and state-transition tests
│   └── test_websockets.py      Real-time delivery and authorization tests
├── README.md
└── requirements.txt
```

## Install and run

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. API documentation is available at <http://127.0.0.1:8000/docs>.

Run one Uvicorn worker. WebSocket connections are stored in this process; production multi-worker deployments need a shared broker such as Redis.

## Try it with two browser tabs

1. Open the app in two tabs.
2. In tab 1, enter user ID `1` and click **Connect**.
3. In tab 2, enter user ID `2` and click **Connect**.
4. In tab 1, set receiver ID `2`, enter a message, and click **Send Message**.
5. Tab 2 receives `NEW_MESSAGE_NOTIFICATION` and automatically sends `DELIVERED`.
6. Tab 1 receives `MESSAGE_DELIVERED`.
7. To mark the message read, use Swagger UI or run:

```powershell
Invoke-RestMethod -Method Patch "http://127.0.0.1:8000/api/messages/1/read?user_id=2"
```

Replace `1` with the actual message ID. Tab 1 then receives `MESSAGE_READ`.

Use **Fetch Messages** and **Fetch Notifications** to inspect saved records. Logs can be cleared independently of the stored data.

## Message statuses

- `SENT`: the backend saved the message. An offline receiver remains at this status because this MVP does not replay pending WebSocket events.
- `DELIVERED`: a currently connected receiver browser received the event and acknowledged it.
- `READ`: the receiver marked the message as read. Marking a `SENT` message read also records delivery, because reading proves delivery.

Status transitions are monotonic. Duplicate delivery acknowledgments and read requests do not change timestamps or send duplicate receipts.

## API notes and assumptions

- Messages and notifications are returned newest first.
- Every active tab connected under a user ID receives that user's events.
- The notification read endpoint only takes a notification ID. Without authentication, anyone who knows that ID can mark it read.
- WebSocket path IDs are treated as identity only for this demo; they are not secure authentication.
- Data is stored in `notifications.db` in the working directory. Set `DATABASE_URL` to use another SQLAlchemy database URL.

## Run tests

```powershell
python -m pytest
```

## Future improvements

- Real authentication and authorization
- PostgreSQL plus migrations
- Redis-backed multi-worker WebSocket fan-out
- Real SMS delivery using Twilio
- Mobile push notifications
- A Spring Boot/Java version
