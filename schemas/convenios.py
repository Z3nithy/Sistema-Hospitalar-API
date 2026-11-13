from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from schemas.evolucao import SaidaComHorario
from schemas.hospital import Entrada, Saida


class PlanoCriar(Entrada):
    convenio_id: int = Field(gt=0)
    nome: str = Field(min_length=1, max_length=120)
    ativo: bool = True


class PlanoSaida(PlanoCriar, Saida):
    id: int


class Ativacao(Entrada):
    ativo: bool


class ProcedimentoCriar(Entrada):
    codigo: str = Field(min_length=1, max_length=40)
    descricao: str = Field(min_length=1, max_length=500)


class ProcedimentoSaida(ProcedimentoCriar, Saida):
    id: int


class CoberturaCriar(Entrada):
    plano_id: int = Field(gt=0)
    procedimento_id: int = Field(gt=0)
    ativa: bool = True


class CoberturaSaida(CoberturaCriar, Saida):
    id: int


class CoberturaAtualizar(Entrada):
    ativa: bool


class Vigencia(Entrada):
    inicio: date
    fim: date
    ativa: bool = True

    @model_validator(mode="after")
    def validar_periodo(self):
        if self.fim < self.inicio:
            raise ValueError("Fim deve ser igual ou posterior ao inicio")
        return self


class CarteirinhaCriar(Vigencia):
    paciente_id: int = Field(gt=0)
    plano_id: int = Field(gt=0)
    numero: str = Field(min_length=1, max_length=80)


class CarteirinhaSaida(CarteirinhaCriar, Saida):
    id: int


class AutorizacaoCriar(Entrada):
    carteirinha_id: int = Field(gt=0)
    procedimento_id: int = Field(gt=0)
    idempotencia: UUID


class AutorizacaoSaida(SaidaComHorario):
    id: int
    carteirinha_id: int
    paciente_id: int
    procedimento_id: int
    usuario_id: int
    idempotencia: UUID
    data_referencia: date
    data_hora: datetime
    status: Literal["aprovada", "negada"]
    motivo: str


class GuiaCriar(Entrada):
    autorizacao_id: int = Field(gt=0)
    cobranca_id: int = Field(gt=0)


class GuiaSaida(SaidaComHorario):
    id: int
    autorizacao_id: int
    cobranca_id: int
    paciente_id: int
    usuario_id: int
    data_hora: datetime
    status: Literal["rascunho", "aceita", "rejeitada"]


class EnvioGuia(Entrada):
    idempotencia: UUID


class TentativaSaida(SaidaComHorario):
    id: int
    guia_id: int
    usuario_id: int
    idempotencia: UUID
    data_referencia: date
    data_hora: datetime
    status: Literal["aceita", "rejeitada"]
    motivo: str
