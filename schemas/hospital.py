from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Perfil(str, Enum):
    admin = "admin"
    medico = "medico"
    enfermagem = "enfermagem"
    recepcao = "recepcao"


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Saida(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Login(Entrada):
    login: str = Field(min_length=1, max_length=80)
    senha: str = Field(min_length=1, max_length=256)


class UsuarioCriar(Entrada):
    nome: str = Field(min_length=1, max_length=120)
    login: str = Field(min_length=1, max_length=80)
    senha: str = Field(min_length=8, max_length=256)
    perfil: Perfil


class UsuarioSaida(Saida):
    id: int
    nome: str
    login: str
    perfil: Perfil
    ativo: bool
    profissional_id: int | None


class PacienteCriar(Entrada):
    nome: str = Field(min_length=1, max_length=120)
    documento: str = Field(min_length=1, max_length=40)
    nascimento: date
    telefone: str | None = Field(default=None, max_length=30)


class PacienteSaida(PacienteCriar, Saida):
    id: int


class ProfissionalCriar(Entrada):
    nome: str = Field(min_length=1, max_length=120)
    registro: str = Field(min_length=1, max_length=40)
    especialidade: str = Field(min_length=1, max_length=80)


class ProfissionalSaida(ProfissionalCriar, Saida):
    id: int


class EventoCriar(Entrada):
    paciente_id: int = Field(gt=0)
    profissional_id: int = Field(gt=0)
    data_hora: datetime

    @field_validator("data_hora")
    @classmethod
    def horario_com_fuso(cls, valor: datetime) -> datetime:
        if valor.utcoffset() is None:
            raise ValueError("Informe data e hora com fuso horario")
        return valor.astimezone(timezone.utc)


class EventoSaida(EventoCriar, Saida):
    @field_validator("data_hora", mode="before")
    @classmethod
    def restaurar_fuso_utc(cls, valor: datetime) -> datetime:
        if isinstance(valor, datetime) and valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor


class ConsultaCriar(EventoCriar):
    motivo: str = Field(min_length=1, max_length=500)
    duracao_minutos: int = Field(default=30, ge=1, le=480)


class ConsultaSaida(ConsultaCriar, EventoSaida):
    id: int
    status: str


class ProntuarioCriar(EventoCriar):
    descricao: str = Field(min_length=1, max_length=10000)


class ProntuarioSaida(ProntuarioCriar, EventoSaida):
    id: int


class LeitoCriar(Entrada):
    codigo: str = Field(min_length=1, max_length=40)
    setor: str = Field(min_length=1, max_length=80)


class LeitoSaida(LeitoCriar, Saida):
    id: int


class InternacaoCriar(Entrada):
    paciente_id: int = Field(gt=0)
    leito_id: int = Field(gt=0)
    profissional_id: int = Field(gt=0)


class InternacaoSaida(Saida):
    id: int
    paciente_id: int
    leito_id: int
    profissional_id: int | None
    entrada: datetime
    alta: datetime | None

    @field_validator("entrada", "alta", mode="before")
    @classmethod
    def restaurar_fuso_utc(cls, valor: datetime | None) -> datetime | None:
        if isinstance(valor, datetime) and valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor


class PrescricaoCriar(EventoCriar):
    medicamento: str = Field(min_length=1, max_length=120)
    medicamento_id: int | None = Field(default=None, gt=0)
    orientacoes: str = Field(min_length=1, max_length=10000)


class PrescricaoSaida(PrescricaoCriar, EventoSaida):
    id: int


class ExameCriar(EventoCriar):
    tipo: str = Field(min_length=1, max_length=120)


class ExameSaida(ExameCriar, EventoSaida):
    id: int
    resultado: str | None


class ResultadoExame(Entrada):
    resultado: str = Field(min_length=1, max_length=10000)
