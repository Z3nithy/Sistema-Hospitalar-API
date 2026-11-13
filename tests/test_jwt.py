import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from jose import jwt

from core.config import ALGORITHM, SECRET_KEY
from core.jwt import criar_token_acesso, verificar_token_acesso


def test_access_token_round_trip() -> None:
    token = criar_token_acesso(42)

    assert verificar_token_acesso(token) == 42


def test_invalid_access_token_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        verificar_token_acesso("not-a-valid-token")

    assert error.value.status_code == 401


def test_legacy_token_without_revocation_version_is_rejected() -> None:
    token = jwt.encode({"sub": "42", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as error:
        verificar_token_acesso(token)
    assert error.value.status_code == 401
