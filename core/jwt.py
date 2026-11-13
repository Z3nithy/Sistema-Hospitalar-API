from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from jose import JWTError, jwt
from .config import SECRET_KEY, ALGORITHM

TEMPO_EXPIRACAO = 60  # minutos


def criar_token_acesso(usuario_id: int, versao_token: int = 0) -> str:
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=TEMPO_EXPIRACAO)

    payload = {
        "sub": str(usuario_id),
        "exp": expiracao,
        "ver": versao_token,
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


def ler_token_acesso(token: str) -> tuple[int, int]:
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require_exp": True},
        )

        usuario_id = payload.get("sub")

        versao = payload.get("ver")
        if not isinstance(usuario_id, str) or not usuario_id.isdecimal() or type(versao) is not int or versao < 0:
            raise HTTPException(status_code=401, detail="Token inválido ou expirado")

        return int(usuario_id), versao

    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")


def verificar_token_acesso(token: str) -> int:
    return ler_token_acesso(token)[0]