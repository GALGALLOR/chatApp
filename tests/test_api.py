def create_message(client, sender_id=1, receiver_id=2, content="Hello"):
    return client.post(
        "/api/messages",
        json={"sender_id": sender_id, "receiver_id": receiver_id, "content": content},
    )


def test_frontend_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Notification & Messaging MVP" in response.text


def test_create_and_fetch_message_and_notification(client):
    response = create_message(client, content="  Hello there  ")
    assert response.status_code == 201
    body = response.json()
    assert body["message"]["content"] == "Hello there"
    assert body["message"]["status"] == "SENT"
    assert body["notification"]["user_id"] == 2
    assert body["receiver_online"] is False

    assert len(client.get("/api/messages/1").json()) == 1
    notifications = client.get("/api/notifications/2").json()
    assert len(notifications) == 1

    marked = client.patch(f"/api/notifications/{notifications[0]['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True


def test_message_validation(client):
    assert create_message(client, sender_id=1, receiver_id=1).status_code == 422
    assert create_message(client, content="   ").status_code == 422
    assert create_message(client, sender_id=0).status_code == 422
    assert client.get("/api/messages/0").status_code == 422


def test_read_is_authorized_monotonic_and_idempotent(client):
    message_id = create_message(client).json()["message"]["id"]
    assert client.patch(f"/api/messages/{message_id}/read?user_id=3").status_code == 403

    first = client.patch(f"/api/messages/{message_id}/read?user_id=2")
    assert first.status_code == 200
    assert first.json()["status"] == "READ"
    assert first.json()["delivered_at"] is not None
    assert first.json()["read_at"] is not None

    second = client.patch(f"/api/messages/{message_id}/read?user_id=2")
    assert second.status_code == 200
    assert second.json()["read_at"] == first.json()["read_at"]


def test_missing_resources_return_404(client):
    assert client.patch("/api/notifications/999/read").status_code == 404
    assert client.patch("/api/messages/999/read?user_id=2").status_code == 404
