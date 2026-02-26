from types import SimpleNamespace

from system.initializer import StationInitializer


def test_load_or_generate_ticket_keys_respects_redemption_only_mode():
    settings = SimpleNamespace(
        storage_type="sqlite",
        token_public_key="public-only-key",
        token_private_key=None,
    )

    initializer = StationInitializer(settings=settings, identity=object())
    public_key, private_key = initializer._load_or_generate_ticket_keys()

    assert public_key == "public-only-key"
    assert private_key is None
