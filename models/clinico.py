from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Alergia(Base):
    __tablename__ = "alergias"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    agente: Mapped[str] = mapped_column(String(120))
    reacao: Mapped[str] = mapped_column(String(500))
    gravidade: Mapped[str] = mapped_column(String(20))


class Diagnostico(Base):
    __tablename__ = "diagnosticos"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    codigo: Mapped[str] = mapped_column(String(30))
    descricao: Mapped[str] = mapped_column(String(500))


class EvolucaoClinica(Base):
    __tablename__ = "evolucoes_clinicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subjetivo: Mapped[str] = mapped_column(Text)
    objetivo: Mapped[str] = mapped_column(Text)
    avaliacao: Mapped[str] = mapped_column(Text)
    plano: Mapped[str] = mapped_column(Text)


class AdministracaoMedicamento(Base):
    __tablename__ = "administracoes_medicamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    prescricao_id: Mapped[int] = mapped_column(ForeignKey("prescricoes.id"))
    lote_id: Mapped[int] = mapped_column(ForeignKey("lotes_medicamentos.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    movimentacao_id: Mapped[int | None] = mapped_column(ForeignKey("movimentacoes_estoque.id"), unique=True)
    idempotencia: Mapped[str] = mapped_column(String(36), unique=True)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quantidade: Mapped[int] = mapped_column()
    dose: Mapped[str] = mapped_column(String(120))
    via: Mapped[str] = mapped_column(String(80))
