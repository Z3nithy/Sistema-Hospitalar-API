import hashlib
import hmac
import time

from fastapi import HTTPException, Request
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as insert_postgresql
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.orm import Session

from core.config import SECRET_KEY
from models import LimiteLogin

LIMITE = 5
JANELA = 15 * 60


def identificador_ip(request: Request) -> str:
    if request.client is None or not request.client.host:
        raise HTTPException(status_code=503, detail="Endereco do cliente indisponivel")
    chave = hmac.new(SECRET_KEY.encode(), b"limite-login:v1", hashlib.sha256).digest()
    return hmac.new(chave, request.client.host.encode(), hashlib.sha256).hexdigest()


def recusar_ate(instante: int, agora: int) -> None:
    raise HTTPException(
        status_code=429,
        detail="Muitas tentativas de login; tente novamente mais tarde",
        headers={"Retry-After": str(max(1, instante - agora))},
    )


def verificar_limite(db: Session, identificador: str) -> None:
    agora = int(time.time())
    limite = db.get(LimiteLogin, identificador)
    if limite is not None and limite.bloqueado_ate > agora:
        recusar_ate(limite.bloqueado_ate, agora)


def registrar_falha(db: Session, identificador: str) -> None:
    agora = int(time.time())
    db.execute(delete(LimiteLogin).where(
        LimiteLogin.inicio <= agora - JANELA,
        LimiteLogin.bloqueado_ate <= agora,
    ))
    expirou = LimiteLogin.inicio <= agora - JANELA
    nova_contagem = case((expirou, 1), else_=LimiteLogin.tentativas + 1)
    dialeto = db.get_bind().dialect.name
    if dialeto == "sqlite":
        inserir = insert_sqlite
    elif dialeto == "postgresql":
        inserir = insert_postgresql
    else:
        raise RuntimeError("Banco nao suportado pelo limite de login")
    comando = inserir(LimiteLogin).values(
        identificador=identificador, inicio=agora, tentativas=1, bloqueado_ate=0,
    ).on_conflict_do_update(
        index_elements=[LimiteLogin.identificador],
        set_={
            "inicio": case((expirou, agora), else_=LimiteLogin.inicio),
            "tentativas": nova_contagem,
            "bloqueado_ate": case((nova_contagem >= LIMITE, agora + JANELA), else_=0),
        },
        where=LimiteLogin.bloqueado_ate <= agora,
    )
    resultado = db.execute(comando)
    if resultado.rowcount == 0:
        bloqueado_ate = db.scalar(select(LimiteLogin.bloqueado_ate).where(
            LimiteLogin.identificador == identificador
        ))
        db.commit()
        if bloqueado_ate is None:
            raise RuntimeError("Registro de limite de login indisponivel")
        recusar_ate(bloqueado_ate, agora)
    db.commit()


def registrar_sucesso(db: Session, identificador: str) -> None:
    agora = int(time.time())
    db.execute(delete(LimiteLogin).where(
        LimiteLogin.identificador == identificador,
        LimiteLogin.bloqueado_ate <= agora,
    ))
    bloqueado_ate = db.scalar(select(LimiteLogin.bloqueado_ate).where(
        LimiteLogin.identificador == identificador
    ))
    db.commit()
    if bloqueado_ate is not None and bloqueado_ate > agora:
        recusar_ate(bloqueado_ate, agora)
