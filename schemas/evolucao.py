from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from schemas.hospital import Entrada, Saida


class SaidaComHorario(Saida):
    @field_validator("data_hora", mode="before", check_fields=False)
    @classmethod
    def restaurar_fuso(cls, valor: datetime) -> datetime:
        if isinstance(valor, datetime) and valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor


class VincularProfissional(Entrada):
    profissional_id: int = Field(gt=0)


class VinculoCriar(Entrada):
    profissional_id: int = Field(gt=0)
    paciente_id: int = Field(gt=0)


class VinculoSaida(VinculoCriar, Saida):
    id: int


class DisponibilidadeCriar(Entrada):
    profissional_id: int = Field(gt=0)
    inicio: datetime
    fim: datetime

    @field_validator("inicio", "fim")
    @classmethod
    def horario_com_fuso(cls, valor: datetime) -> datetime:
        if valor.utcoffset() is None:
            raise ValueError("Informe data e hora com fuso horario")
        return valor.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validar_periodo(self):
        if self.fim <= self.inicio:
            raise ValueError("Fim deve ser posterior ao inicio")
        return self


class DisponibilidadeSaida(DisponibilidadeCriar, Saida):
    id: int

    @field_validator("inicio", "fim", mode="before")
    @classmethod
    def restaurar_fuso(cls, valor: datetime) -> datetime:
        if isinstance(valor, datetime) and valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor


class AuditoriaSaida(SaidaComHorario):
    id: int
    usuario_id: int
    acao: str
    recurso: str
    registro_id: int
    data_hora: datetime


class MedicamentoCriar(Entrada):
    nome: str = Field(min_length=1, max_length=120)
    estoque_minimo: int = Field(default=0, ge=0, le=2147483647)


class MedicamentoSaida(MedicamentoCriar, Saida):
    id: int
    quantidade: int
    quantidade_nao_rastreada: int


class EstoqueMinimo(Entrada):
    estoque_minimo: int = Field(ge=0, le=2147483647)


class LoteCriar(Entrada):
    medicamento_id: int = Field(gt=0)
    codigo: str = Field(min_length=1, max_length=80)
    validade: date


class LoteSaida(LoteCriar, Saida):
    id: int
    quantidade: int


class EstoqueAlerta(Entrada):
    medicamento_id: int
    nome: str
    estoque_minimo: int
    quantidade_disponivel: int


class MovimentacaoCriar(Entrada):
    medicamento_id: int = Field(gt=0)
    lote_id: int = Field(gt=0)
    tipo: Literal["entrada", "saida", "descarte"]
    quantidade: int = Field(gt=0, le=1000000)


class RegularizacaoCriar(Entrada):
    lote_id: int = Field(gt=0)
    quantidade: int = Field(gt=0, le=1000000)


class MovimentacaoSaida(SaidaComHorario):
    id: int
    medicamento_id: int
    lote_id: int | None
    tipo: Literal["entrada", "saida", "descarte", "regularizacao"]
    quantidade: int
    usuario_id: int
    data_hora: datetime


class ConvenioCriar(Entrada):
    nome: str = Field(min_length=1, max_length=120)


class ConvenioSaida(ConvenioCriar, Saida):
    id: int


class CobrancaCriar(Entrada):
    paciente_id: int = Field(gt=0)
    convenio_id: int | None = Field(default=None, gt=0)
    descricao: str = Field(min_length=1, max_length=500)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class CobrancaSaida(CobrancaCriar, Saida):
    id: int
    valor_pago: Decimal


class PagamentoCriar(Entrada):
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PagamentoSaida(SaidaComHorario):
    id: int
    cobranca_id: int
    usuario_id: int
    valor: Decimal
    data_hora: datetime
