from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from models import LoteMedicamento, Medicamento, MovimentacaoEstoque, User
from services.hospital import buscar


def preparar_movimentacao(
    db: Session, usuario: User, medicamento_id: int, lote_id: int, tipo: Literal["entrada", "saida", "descarte"], quantidade: int,
) -> MovimentacaoEstoque:
    buscar(db, Medicamento, medicamento_id)
    lote = buscar(db, LoteMedicamento, lote_id)
    if lote.medicamento_id != medicamento_id:
        raise HTTPException(status_code=422, detail="Lote nao pertence ao medicamento")
    if tipo == "saida" and lote.validade < datetime.now(timezone.utc).date():
        raise HTTPException(status_code=409, detail="Lote vencido")
    mudanca = quantidade if tipo == "entrada" else -quantidade
    condicao = Medicamento.quantidade <= 2147483647 - quantidade if mudanca > 0 else Medicamento.quantidade >= quantidade
    resultado = db.execute(update(Medicamento).where(
        Medicamento.id == medicamento_id, condicao,
    ).values(quantidade=Medicamento.quantidade + mudanca))
    if resultado.rowcount != 1:
        raise HTTPException(status_code=409, detail="Quantidade de estoque invalida")
    condicao_lote = LoteMedicamento.quantidade <= 2147483647 - quantidade if mudanca > 0 else LoteMedicamento.quantidade >= quantidade
    resultado_lote = db.execute(update(LoteMedicamento).where(
        LoteMedicamento.id == lote_id, condicao_lote,
    ).values(quantidade=LoteMedicamento.quantidade + mudanca))
    if resultado_lote.rowcount != 1:
        raise HTTPException(status_code=409, detail="Quantidade do lote invalida")
    return MovimentacaoEstoque(
        medicamento_id=medicamento_id, lote_id=lote_id, tipo=tipo,
        quantidade=quantidade, usuario_id=usuario.id, data_hora=datetime.now(timezone.utc),
    )
