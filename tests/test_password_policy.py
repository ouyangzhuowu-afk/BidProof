from pydantic import ValidationError

from app.schemas import (
    MIN_PASSWORD_LENGTH,
    PASSWORD_POLICY_MESSAGE,
    PersonalRegisterRequest,
    password_meets_policy,
)


def test_password_policy_accepts_letter_and_digit_at_least_eight():
    assert MIN_PASSWORD_LENGTH == 8
    assert password_meets_policy("abc12345")
    assert password_meets_policy("Passw0rd")
    assert not password_meets_policy("short1")  # under 8
    assert not password_meets_policy("abcdefgh")  # letters only
    assert not password_meets_policy("12345678")  # digits only
    assert not password_meets_policy("密码密码12")  # non-ASCII letters do not count


def test_register_schema_rejects_password_without_letter_and_digit():
    try:
        PersonalRegisterRequest(username="user123", password="abcdefgh")
        raise AssertionError("expected ValidationError")
    except ValidationError as exc:
        assert PASSWORD_POLICY_MESSAGE in str(exc)

    ok = PersonalRegisterRequest(username="user123", password="abcd1234")
    assert ok.password == "abcd1234"
