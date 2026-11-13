from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from dependencies.autenticacao import OPERACOES_RECURSOS, exigir_perfis
from models import EventoSeguranca, RestricaoOperacao, RestricaoRecurso, User
from schemas.evolucao import SaidaComHorario
from services.hospital import auditar, buscar

router = APIRouter()
admin = exigir_perfis("admin")


class PermissaoAlterar(BaseModel):
    permitida: bool


class EventoSegurancaSaida(SaidaComHorario):
    id: int
    usuario_id: int | None
    alvo_usuario_id: int | None
    evento: str
    operacao: str
    data_hora: datetime


def operacoes_disponiveis(request: Request) -> list[dict]:
    operacoes = []
    for rota in (rota for router in request.app.state.routers_permissoes for rota in router.routes):
        if isinstance(rota, APIRoute) and any(
            getattr(dependencia.call, "__name__", "") == "verificar"
            for dependencia in rota.dependant.dependencies
        ):
            operacoes.append({"operacao": rota.name, "metodos": sorted(rota.methods), "caminho": rota.path})
    return sorted(operacoes, key=lambda item: item["operacao"])


@router.get("/operacoes", tags=["permissoes"])
def listar_operacoes(request: Request, usuario: User = Depends(admin)):
    return operacoes_disponiveis(request)


@router.get("/usuarios/{identificador}/permissoes", tags=["permissoes"])
def listar_restricoes(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    buscar(db, User, identificador)
    return {"restricoes": db.scalars(select(RestricaoOperacao.operacao).where(
        RestricaoOperacao.usuario_id == identificador
    ).order_by(RestricaoOperacao.operacao)).all()}


@router.put("/usuarios/{identificador}/permissoes/{operacao}", tags=["permissoes"])
def alterar_restricao(
    identificador: int,
    operacao: str,
    dados: PermissaoAlterar,
    request: Request,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    alvo = buscar(db, User, identificador)
    if alvo.perfil == "admin":
        raise HTTPException(status_code=403, detail="Administradores nao podem ser restringidos")
    if operacao not in {item["operacao"] for item in operacoes_disponiveis(request)}:
        raise HTTPException(status_code=404, detail="Operacao nao encontrada")
    restricao = db.scalar(select(RestricaoOperacao).where(
        RestricaoOperacao.usuario_id == identificador,
        RestricaoOperacao.operacao == operacao,
    ))
    if dados.permitida and restricao is not None:
        db.delete(restricao)
    elif not dados.permitida and restricao is None:
        db.add(RestricaoOperacao(usuario_id=identificador, operacao=operacao))
    auditar(db, usuario, "permissao", alvo)
    db.add(EventoSeguranca(
        usuario_id=usuario.id, alvo_usuario_id=identificador,
        evento="operacao_permitida" if dados.permitida else "operacao_bloqueada",
        operacao=operacao, data_hora=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"operacao": operacao, "permitida": dados.permitida}


@router.get("/usuarios/{identificador}/recursos", tags=["permissoes"])
def listar_recursos(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    buscar(db, User, identificador)
    restritos = db.scalars(select(RestricaoRecurso.recurso).where(
        RestricaoRecurso.usuario_id == identificador
    ).order_by(RestricaoRecurso.recurso)).all()
    return {"disponiveis": sorted(OPERACOES_RECURSOS), "restritos": restritos}


@router.put("/usuarios/{identificador}/recursos/{recurso}", tags=["permissoes"])
def alterar_recurso(
    identificador: int,
    recurso: str,
    dados: PermissaoAlterar,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    alvo = buscar(db, User, identificador)
    if alvo.perfil == "admin":
        raise HTTPException(status_code=403, detail="Administradores nao podem ser restringidos")
    if recurso not in OPERACOES_RECURSOS:
        raise HTTPException(status_code=404, detail="Recurso nao encontrado")
    restricao = db.scalar(select(RestricaoRecurso).where(
        RestricaoRecurso.usuario_id == identificador, RestricaoRecurso.recurso == recurso,
    ))
    if dados.permitida and restricao is not None:
        db.delete(restricao)
    elif not dados.permitida and restricao is None:
        db.add(RestricaoRecurso(usuario_id=identificador, recurso=recurso))
    auditar(db, usuario, "permissao", alvo)
    db.add(EventoSeguranca(
        usuario_id=usuario.id, alvo_usuario_id=identificador,
        evento="recurso_permitido" if dados.permitida else "recurso_bloqueado",
        operacao=recurso, data_hora=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"recurso": recurso, "permitida": dados.permitida}


@router.get("/eventos-seguranca", response_model=list[EventoSegurancaSaida], tags=["auditoria"])
def listar_eventos_seguranca(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    return db.scalars(select(EventoSeguranca).order_by(
        EventoSeguranca.id
    ).offset(offset).limit(limit)).all()
