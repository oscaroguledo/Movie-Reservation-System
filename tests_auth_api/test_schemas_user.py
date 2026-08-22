import pytest
from pydantic import ValidationError
from schemas.user import UserCreate, UserGet, UserList, UserLogin, UserUpdate

VALID_PASSWORD = "StrongPassw0rd!"

WEAK_PASSWORDS = [
    "short1!",  # too short
    "alllowercase1!",  # no uppercase
    "ALLUPPERCASE1!",  # no lowercase
    "NoDigitsHere!",  # no digit
    "NoSpecialChar123",  # no special character
]


class TestUserCreate:
    def test_accepts_a_valid_payload(self):
        user = UserCreate(
            email="jane@example.com",
            first_name="Jane",
            last_name="Doe",
            password=VALID_PASSWORD,
        )

        assert user.type == "regular"

    def test_defaults_type_to_regular(self):
        user = UserCreate(
            email="jane@example.com",
            first_name="Jane",
            last_name="Doe",
            password=VALID_PASSWORD,
        )

        assert user.type == "regular"

    def test_rejects_invalid_type(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="jane@example.com",
                first_name="Jane",
                last_name="Doe",
                password=VALID_PASSWORD,
                type="superadmin",
            )

    def test_rejects_invalid_email(self):
        with pytest.raises(ValidationError):
            UserCreate(
                email="not-an-email",
                first_name="Jane",
                last_name="Doe",
                password=VALID_PASSWORD,
            )

    @pytest.mark.parametrize("password", WEAK_PASSWORDS)
    def test_rejects_passwords_missing_a_complexity_rule(self, password):
        with pytest.raises(ValidationError):
            UserCreate(
                email="jane@example.com", first_name="Jane", last_name="Doe", password=password
            )


class TestUserLogin:
    def test_accepts_a_valid_payload(self):
        login = UserLogin(email="jane@example.com", password=VALID_PASSWORD)

        assert login.email == "jane@example.com"

    @pytest.mark.parametrize("password", WEAK_PASSWORDS)
    def test_rejects_passwords_missing_a_complexity_rule(self, password):
        with pytest.raises(ValidationError):
            UserLogin(email="jane@example.com", password=password)


class TestUserGet:
    def test_accepts_id_only(self):
        UserGet(id="123e4567-e89b-12d3-a456-426614174000")

    def test_accepts_email_only(self):
        UserGet(email="jane@example.com")

    def test_rejects_when_no_field_provided(self):
        with pytest.raises(ValidationError, match="At least one of"):
            UserGet()


class TestUserList:
    def test_accepts_a_single_filter(self):
        UserList(type="admin")

    def test_rejects_when_no_filter_provided(self):
        with pytest.raises(ValidationError, match="At least one of"):
            UserList()


class TestUserUpdate:
    def test_allows_all_fields_omitted(self):
        update = UserUpdate()

        assert update.password is None

    def test_allows_explicit_null_password(self):
        update = UserUpdate(password=None)

        assert update.password is None

    @pytest.mark.parametrize("password", WEAK_PASSWORDS)
    def test_rejects_passwords_missing_a_complexity_rule(self, password):
        with pytest.raises(ValidationError):
            UserUpdate(password=password)

    def test_accepts_a_strong_password(self):
        update = UserUpdate(password=VALID_PASSWORD)

        assert update.password == VALID_PASSWORD
