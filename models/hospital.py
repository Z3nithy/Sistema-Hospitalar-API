from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class User(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    login: Mapped[str] = mapped_column(String(80), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    perfil: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(default=True)
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissionais.id", name="fk_usuarios_profissional"), unique=True)
    versao_token: Mapped[int] = mapped_column(default=0, server_default="0")


class Paciente(Base):
    __tablename__ = "pacientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    documento: Mapped[str] = mapped_column(String(40), unique=True)
    nascimento: Mapped[date] = mapped_column(Date)
    telefone: Mapped[str | None] = mapped_column(String(30))


class Profissional(Base):
    __tablename__ = "profissionais"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    registro: Mapped[str] = mapped_column(String(40), unique=True)
    especialidade: Mapped[str] = mapped_column(String(80))
    versao_agenda: Mapped[int] = mapped_column(default=0, server_default="0")


class Consulta(Base):
    __tablename__ = "consultas"
    __table_args__ = (
        UniqueConstraint("profissional_id", "horario_ativo", name="uq_consulta_profissional_horario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horario_ativo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="agendada")
    duracao_minutos: Mapped[int] = mapped_column(default=30, server_default="30")


class Prontuario(Base):
    __tablename__ = "prontuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    descricao: Mapped[str] = mapped_column(Text)


class Leito(Base):
    __tablename__ = "leitos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    setor: Mapped[str] = mapped_column(String(80))


class Internacao(Base):
    __tablename__ = "internacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    leito_id: Mapped[int] = mapped_column(ForeignKey("leitos.id"))
    profissional_id: Mapped[int | None] = mapped_column(ForeignKey("profissionais.id", name="fk_internacoes_profissional"))
    entrada: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    alta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paciente_ativo_id: Mapped[int | None] = mapped_column(ForeignKey("pacientes.id"), unique=True)
    leito_ativo_id: Mapped[int | None] = mapped_column(ForeignKey("leitos.id"), unique=True)


class Prescricao(Base):
    __tablename__ = "prescricoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    medicamento: Mapped[str] = mapped_column(String(120))
    medicamento_id: Mapped[int | None] = mapped_column(ForeignKey("medicamentos.id", name="fk_prescricoes_medicamento"))
    orientacoes: Mapped[str] = mapped_column(Text)


class Exame(Base):
    __tablename__ = "exames"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    tipo: Mapped[str] = mapped_column(String(120))
    resultado: Mapped[str | None] = mapped_column(Text)
