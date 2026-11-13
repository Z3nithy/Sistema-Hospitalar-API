from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import Auditoria, Consulta, Disponibilidade, Profissional, User, VinculoPaciente


def salvar(db: Session, objeto, usuario: User | None = None, acao: str = "criar", vinculo=None):
    db.add(objeto)
    try:
        db.flush()
        if usuario is not None:
            auditar(db, usuario, acao, objeto)
            if vinculo is not None:
                auditar(db, usuario, "criar", vinculo)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito de dados ou referencia inexistente") from exc
    db.refresh(objeto)
    return objeto


def buscar(db: Session, modelo, identificador: int):
    objeto = db.get(modelo, identificador)
    if objeto is None:
        raise HTTPException(status_code=404, detail="Registro nao encontrado")
    return objeto


def auditar(db: Session, usuario: User, acao: str, objeto) -> None:
    db.add(Auditoria(
        usuario_id=usuario.id,
        acao=acao,
        recurso=objeto.__tablename__,
        registro_id=objeto.id,
        data_hora=datetime.now(timezone.utc),
    ))


def registrar_leitura(db: Session, usuario: User, objetos) -> None:
    for objeto in objetos:
        auditar(db, usuario, "leitura", objeto)
    db.commit()


def pacientes_permitidos(usuario: User):
    return select(VinculoPaciente.paciente_id).where(
        VinculoPaciente.profissional_id == usuario.profissional_id
    )


def verificar_paciente(db: Session, usuario: User, paciente_id: int) -> None:
    if usuario.perfil in ("admin", "recepcao"):
        return
    if usuario.profissional_id is None or db.scalar(
        select(VinculoPaciente.id).where(
            VinculoPaciente.profissional_id == usuario.profissional_id,
            VinculoPaciente.paciente_id == paciente_id,
        )
    ) is None:
        raise HTTPException(status_code=403, detail="Paciente nao vinculado ao profissional")


def verificar_autoria(usuario: User, profissional_id: int) -> None:
    if usuario.perfil != "admin" and usuario.profissional_id != profissional_id:
        raise HTTPException(status_code=403, detail="Profissional nao corresponde ao usuario")


def vincular_paciente(db: Session, profissional_id: int, paciente_id: int) -> VinculoPaciente | None:
    existe = db.scalar(select(VinculoPaciente.id).where(
        VinculoPaciente.profissional_id == profissional_id,
        VinculoPaciente.paciente_id == paciente_id,
    ))
    if existe is None:
        vinculo = VinculoPaciente(profissional_id=profissional_id, paciente_id=paciente_id)
        db.add(vinculo)
        return vinculo
    return None


def utc(valor: datetime) -> datetime:
    if valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def validar_agendamento(db: Session, profissional_id: int, inicio: datetime, duracao: int) -> None:
    # Serializa agendamentos do mesmo profissional antes de consultar conflitos.
    db.execute(update(Profissional).where(Profissional.id == profissional_id).values(
        versao_agenda=Profissional.versao_agenda + 1
    ))
    fim = inicio + timedelta(minutes=duracao)
    janelas = db.scalars(select(Disponibilidade).where(
        Disponibilidade.profissional_id == profissional_id
    )).all()
    if not any(utc(j.inicio) <= inicio and fim <= utc(j.fim) for j in janelas):
        raise HTTPException(status_code=409, detail="Consulta fora da disponibilidade do profissional")
    consultas = db.scalars(select(Consulta).where(
        Consulta.profissional_id == profissional_id,
        Consulta.status != "cancelada",
    )).all()
    if any(utc(c.data_hora) < fim and inicio < utc(c.data_hora) + timedelta(minutes=c.duracao_minutos) for c in consultas):
        raise HTTPException(status_code=409, detail="Horario de consulta indisponivel")
