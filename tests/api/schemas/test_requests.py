import pytest
from pydantic import ValidationError

from schemas.requests import KeyRequestRequest, TicketIssuanceRequest


def test_ticket_issuance_request_valid():
    exactly_100 = [(i, f"b{i}") for i in range(100)]
    req = TicketIssuanceRequest(ticket_request="req-1", blinded_requests=exactly_100)
    assert req.ticket_request == "req-1"
    assert len(req.blinded_requests) == 100


def test_ticket_issuance_request_requires_blinded_requests():
    with pytest.raises(ValidationError):
        TicketIssuanceRequest(ticket_request="req-1", blinded_requests=[])


def test_ticket_issuance_request_exact_count():
    """Validation enforces exactly 100 blinded requests."""
    too_few = [(i, "x") for i in range(2)]
    with pytest.raises(ValidationError):
        TicketIssuanceRequest(ticket_request="req-1", blinded_requests=too_few)

    too_many = [(i, "x") for i in range(101)]
    with pytest.raises(ValidationError):
        TicketIssuanceRequest(ticket_request="req-1", blinded_requests=too_many)


def test_ticket_issuance_request_requires_non_empty_ticket_request():
    with pytest.raises(ValidationError):
        TicketIssuanceRequest(ticket_request="   ", blinded_requests=[(0, "b1")])


def test_key_request_request_positive_validation():
    with pytest.raises(ValidationError):
        KeyRequestRequest(credit_limit=-1)

    with pytest.raises(ValidationError):
        KeyRequestRequest(duration_limit=0)

    ok = KeyRequestRequest(credit_limit=1.5, duration_limit=30)
    assert ok.credit_limit == 1.5
    assert ok.duration_limit == 30
