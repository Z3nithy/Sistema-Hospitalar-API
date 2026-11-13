from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from schemas.hospital import Entrada, EventoCriar, EventoSaida, Saida


class AlergiaCriar(EventoCriar):
    agente: str = Field(min_length=1, max_length=120)
    reacao: str = Field(min_length=1, max_length=500)
    gravidade: Literal["leve", "moderada", "grave", "desconhecida"]


class AlergiaSaida(AlergiaCriar, EventoSaida):
    id: int


class DiagnosticoCriar(EventoCriar):
    codigo: str = Field(min_length=1, max_length=30)
    descricao: str = Field(min_length=1, max_length=500)


class DiagnosticoSaida(DiagnosticoCriar, EventoSaida):
    id: int


class EvolucaoCriar(EventoCriar):
    subjetivo: str = Field(min_length=1, max_length=10000)
    objetivo: str = Field(min_length=1, max_length=10000)
    avaliacao: str = Field(min_length=1, max_length=10000)
    plano: str = Field(min_length=1, max_length=10000)


class EvolucaoSaida(EvolucaoCriar, EventoSaida):
    id: int


class AdministracaoCriar(Entrada):
    prescricao_id: int = Field(gt=0)
    profissional_id: int = Field(gt=0)
    lote_id: int = Field(gt=0)
    idempotencia: UUID
    data_hora: datetime
    quantidade: int = Field(gt=0, le=1000000)
    dose: str = Field(min_length=1, max_length=120)
    via: str = Field(min_length=1, max_length=80)

    @field_validator("data_hora")
    @classmethod
    def horario_com_fuso(cls, valor: datetime) -> datetime:
        if valor.utcoffset() is None:
            raise ValueError("Informe data e hora com fuso horario")
        return valor.astimezone(timezone.utc)


class AdministracaoSaida(Saida):
    id: int
    paciente_id: int
    profissional_id: int
    prescricao_id: int
    lote_id: int
    usuario_id: int
    movimentacao_id: int
    idempotencia: UUID
    data_hora: datetime
    quantidade: int
    dose: str
    via: str

    @field_validator("data_hora", mode="before")
    @classmethod
    def restaurar_fuso(cls, valor: datetime) -> datetime:
        if isinstance(valor, datetime) and valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor
