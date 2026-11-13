from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models import Carteirinha, Cobertura, Plano
from services.hospital import buscar


def bloquear_plano(db: Session, plano_id: int) -> None:
    db.execute(
        update(Plano).where(Plano.id == plano_id).values(versao=Plano.versao + 1)
    )


def avaliar(db: Session, carteirinha: Carteirinha, procedimento_id: int, hoje: date) -> tuple[bool, str]:
    db.refresh(carteirinha)
    plano = buscar(db, Plano, carteirinha.plano_id)
    db.refresh(plano)
    if not plano.ativo:
        return False, "plano_inativo"
    if not carteirinha.ativa:
        return False, "carteirinha_inativa"
    if not carteirinha.inicio <= hoje <= carteirinha.fim:
        return False, "fora_vigencia"
    cobertura = db.scalar(select(Cobertura).where(
        Cobertura.plano_id == plano.id,
        Cobertura.procedimento_id == procedimento_id,
        Cobertura.ativa.is_(True),
    ))
    if cobertura is None:
        return False, "sem_cobertura"
    return True, "aprovada"
