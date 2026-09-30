from appliance.models import event_digest, utcnow
from appliance.security import hash_password, verify_password


def test_password_hashing():
    encoded = hash_password("a-very-long-test-password")
    assert encoded != "a-very-long-test-password"
    assert verify_password(encoded, "a-very-long-test-password")
    assert not verify_password(encoded, "incorrect-password")


def test_audit_digest_changes_with_event():
    created = utcnow()
    first = event_digest(
        actor_id="admin",
        action="mfa.user.created",
        subject_type="mfa_user",
        subject_id="user-1",
        reason=None,
        success=True,
        previous_hash=None,
        created_at=created,
    )
    second = event_digest(
        actor_id="admin",
        action="mfa.user.disabled",
        subject_type="mfa_user",
        subject_id="user-1",
        reason="offboarding",
        success=True,
        previous_hash=first,
        created_at=created,
    )
    assert first != second
