from schemas.responses import KeyRequestResponse, TicketIssuanceResponse


def test_ticket_issuance_response_shape():
    resp = TicketIssuanceResponse(
        signed_responses=[(0, "s1"), (1, "s2")],
        expires_at=0,
        public_key="pk",
    )
    assert resp.signed_responses == [(0, "s1"), (1, "s2")]
    assert resp.expires_at == 0
    assert resp.public_key == "pk"


def test_key_request_response_shape():
    resp = KeyRequestResponse(
        key="sk-abc",
        key_hash="hash123",
        tickets_consumed=2,
        credit_limit=2.0,
        duration_minutes=60,
        expires_at="2026-01-01T00:00:00+00:00",
        expires_at_unix=1767225600,
        station_id="station-local",
        station_signature="deadbeef",
    )
    assert resp.tickets_consumed == 2
    assert resp.key_hash == "hash123"
