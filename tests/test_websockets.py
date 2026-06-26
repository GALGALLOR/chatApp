from concurrent.futures import ThreadPoolExecutor


def test_delivery_acknowledgment_notifies_sender(client):
    with client.websocket_connect("/ws/1") as sender_socket:
        assert sender_socket.receive_json()["type"] == "CONNECTED"
        with client.websocket_connect("/ws/2") as receiver_socket:
            assert receiver_socket.receive_json()["type"] == "CONNECTED"

            with ThreadPoolExecutor() as executor:
                future = executor.submit(
                    client.post,
                    "/api/messages",
                    json={"sender_id": 1, "receiver_id": 2, "content": "Realtime"},
                )
                notification = receiver_socket.receive_json()
                response = future.result(timeout=5)

            assert response.status_code == 201
            assert response.json()["receiver_online"] is True
            assert notification["type"] == "NEW_MESSAGE_NOTIFICATION"
            message_id = notification["message"]["id"]

            receiver_socket.send_json({"type": "DELIVERED", "message_id": message_id})
            assert receiver_socket.receive_json()["type"] == "DELIVERY_ACKNOWLEDGED"
            delivered = sender_socket.receive_json()
            assert delivered == {
                "type": "MESSAGE_DELIVERED",
                "message_id": message_id,
                "receiver_id": 2,
            }

            receiver_socket.send_json({"type": "DELIVERED", "message_id": message_id})
            duplicate = receiver_socket.receive_json()
            assert duplicate["type"] == "DELIVERY_ACKNOWLEDGED"
            assert duplicate["status"] == "DELIVERED"


def test_wrong_receiver_cannot_acknowledge(client):
    message_id = client.post(
        "/api/messages",
        json={"sender_id": 1, "receiver_id": 2, "content": "Private"},
    ).json()["message"]["id"]

    with client.websocket_connect("/ws/3") as socket:
        socket.receive_json()
        socket.send_json({"type": "DELIVERED", "message_id": message_id})
        error = socket.receive_json()
        assert error["type"] == "ERROR"
        assert "receiver" in error["detail"].lower()

    message = client.get("/api/messages/1").json()[0]
    assert message["status"] == "SENT"


def test_all_tabs_for_receiver_get_new_message(client):
    with client.websocket_connect("/ws/2") as first_tab:
        first_tab.receive_json()
        with client.websocket_connect("/ws/2") as second_tab:
            second_tab.receive_json()
            response = client.post(
                "/api/messages",
                json={"sender_id": 1, "receiver_id": 2, "content": "Both tabs"},
            )
            assert response.status_code == 201
            assert response.json()["receiver_online"] is True
            first_event = first_tab.receive_json()
            second_event = second_tab.receive_json()
            assert first_event["type"] == "NEW_MESSAGE_NOTIFICATION"
            assert second_event["message"]["id"] == first_event["message"]["id"]


def test_marking_read_notifies_sender(client):
    message_id = client.post(
        "/api/messages",
        json={"sender_id": 1, "receiver_id": 2, "content": "Read me"},
    ).json()["message"]["id"]

    with client.websocket_connect("/ws/1") as sender_socket:
        sender_socket.receive_json()
        response = client.patch(f"/api/messages/{message_id}/read?user_id=2")
        assert response.status_code == 200
        assert sender_socket.receive_json() == {
            "type": "MESSAGE_READ",
            "message_id": message_id,
            "receiver_id": 2,
        }
