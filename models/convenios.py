from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Plano(Base):
    __tablename__ = "planos_convenio"
    __table_args__ = (UniqueConstraint("convenio_id", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    convenio_id: Mapped[int] = mapped_column(ForeignKey("convenios.id"))
    nome: Mapped[str] = mapped_column(String(120))
    ativo: Mapped[bool] = mapped_column(default=True, server_default="1")
    versao: Mapped[int] = mapped_column(default=0, server_default="0")


class Procedimento(Base):
    __tablename__ = "procedimentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True)
    descricao: Mapped[str] = mapped_column(String(500))


class Cobertura(Base):
    __tablename__ = "coberturas_convenio"
    __table_args__ = (UniqueConstraint("plano_id", "procedimento_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("planos_convenio.id"))
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimentos.id"))
    ativa: Mapped[bool] = mapped_column(default=True, server_default="1")


class Carteirinha(Base):
    __tablename__ = "carteirinhas"
    __table_args__ = (UniqueConstraint("plano_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("planos_convenio.id"))
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    numero: Mapped[str] = mapped_column(String(80))
    inicio: Mapped[date] = mapped_column(Date)
    fim: Mapped[date] = mapped_column(Date)
    ativa: Mapped[bool] = mapped_column(default=True, server_default="1")


class AutorizacaoConvenio(Base):
    __tablename__ = "autorizacoes_convenio"

    id: Mapped[int] = mapped_column(primary_key=True)
    carteirinha_id: Mapped[int] = mapped_column(ForeignKey("carteirinhas.id"))
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    procedimento_id: Mapped[int] = mapped_column(ForeignKey("procedimentos.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    idempotencia: Mapped[str] = mapped_column(String(36), unique=True)
    data_referencia: Mapped[date] = mapped_column(Date)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str] = mapped_column(String(40))


class GuiaConvenio(Base):
    __tablename__ = "guias_convenio"

    id: Mapped[int] = mapped_column(primary_key=True)
    autorizacao_id: Mapped[int] = mapped_column(ForeignKey("autorizacoes_convenio.id"), unique=True)
    cobranca_id: Mapped[int] = mapped_column(ForeignKey("cobrancas.id"), unique=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="rascunho")
    versao: Mapped[int] = mapped_column(default=0, server_default="0")


class TentativaGuia(Base):
    __tablename__ = "tentativas_guia"

    id: Mapped[int] = mapped_column(primary_key=True)
    guia_id: Mapped[int] = mapped_column(ForeignKey("guias_convenio.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    idempotencia: Mapped[str] = mapped_column(String(36), unique=True)
    data_referencia: Mapped[date] = mapped_column(Date)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str] = mapped_column(String(40))
