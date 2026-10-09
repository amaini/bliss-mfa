from appliance.coverage import reconcile
from appliance.models import MfaUser, UserStatus


class FakeEngine:
    def __init__(self, totp=(), fail=()):
        self.kind = {u.lower(): "t" for u in totp}
        self.fail = {f.lower() for f in fail}
        self.deleted = []

    def ensure_without2fa(self, username):
        if username.lower() in self.fail:
            raise RuntimeError("engine down")
        if self.kind.get(username.lower()) == "t":
            return False
        self.kind[username.lower()] = "w"
        return True

    def without2fa_status(self, username):
        k = self.kind.get(username.lower())
        return {"without2fa": k == "w", "exists": k is not None}

    def delete_user(self, username):
        self.deleted.append(username)
        self.kind.pop(username.lower(), None)
        return True

    def create_user(self, username):
        self.kind[username.lower()] = "t"

    def provisioning_uri(self, username):
        return f"otpauth://totp/Bliss:{username}?secret=TESTONLY"

    def verify(self, username, otp):
        return otp == "000000"


ACCOUNTS = [
    {"username": "Abhishek", "display_name": None, "enabled": True},
    {"username": "Ekta", "display_name": None, "enabled": True},
    {"username": "JSmith", "display_name": None, "enabled": True},
    {"username": "Pending", "display_name": None, "enabled": True},
    {"username": "Gone", "display_name": None, "enabled": True},
    {"username": "Guest", "display_name": None, "enabled": False},
]


def user(name, status):
    return MfaUser(username=name, engine_username=name, status=status)


def test_rows_of_the_coverage_table():
    engine = FakeEngine(totp=["jsmith", "pending", "gone"])
    users = [user("jsmith", UserStatus.active), user("Pending", UserStatus.pending), user("Gone", UserStatus.revoked)]
    result = reconcile(ACCOUNTS, users, engine, recovery="ABHISHEK")
    assert result["protected"] == ["JSmith", "Pending"]
    assert sorted(result["password_only"]) == ["Ekta", "Gone"]
    assert engine.kind["ekta"] == "w" and engine.kind["gone"] == "w"
    assert engine.deleted == ["Gone"]
    assert "abhishek" not in engine.kind and "guest" not in engine.kind
    assert engine.kind["jsmith"] == "t"


def test_one_failure_does_not_stop_others():
    engine = FakeEngine(fail=["Ekta"])
    result = reconcile(ACCOUNTS[:3], [], engine, recovery="Abhishek")
    assert result["errors"] == ["Ekta"] and result["password_only"] == ["JSmith"]


def test_unexpected_totp_without_bliss_record_is_left_alone():
    engine = FakeEngine(totp=["ekta"])
    result = reconcile(ACCOUNTS[1:2], [], engine, recovery=None)
    assert result["errors"] == ["Ekta"] and engine.deleted == []
