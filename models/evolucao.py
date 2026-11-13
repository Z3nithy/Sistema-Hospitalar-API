from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class VinculoPaciente(Base):
    __tablename__ = "vinculos_pacientes"
    __table_args__ = (UniqueConstraint("profissional_id", "paciente_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))


class Disponibilidade(Base):
    __tablename__ = "disponibilidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    profissional_id: Mapped[int] = mapped_column(ForeignKey("profissionais.id"))
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fim: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    acao: Mapped[str] = mapped_column(String(20))
    recurso: Mapped[str] = mapped_column(String(40))
    registro_id: Mapped[int] = mapped_column()
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventoSeguranca(Base):
    __tablename__ = "eventos_seguranca"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    alvo_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    evento: Mapped[str] = mapped_column(String(40))
    operacao: Mapped[str] = mapped_column(String(100))
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RestricaoOperacao(Base):
    __tablename__ = "restricoes_operacoes"
    __table_args__ = (UniqueConstraint("usuario_id", "operacao"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    operacao: Mapped[str] = mapped_column(String(100))


class RestricaoRecurso(Base):
    __tablename__ = "restricoes_recursos"
    __table_args__ = (UniqueConstraint("usuario_id", "recurso"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    recurso: Mapped[str] = mapped_column(String(40))


class LimiteLogin(Base):
    __tablename__ = "limites_login"

    identificador: Mapped[str] = mapped_column(String(64), primary_key=True)
    inicio: Mapped[int] = mapped_column(BigInteger)
    tentativas: Mapped[int] = mapped_column()
    bloqueado_ate: Mapped[int] = mapped_column(BigInteger)


class Medicamento(Base):
    __tablename__ = "medicamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)
    quantidade: Mapped[int] = mapped_column(default=0, server_default="0")
    quantidade_nao_rastreada: Mapped[int] = mapped_column(default=0, server_default="0")
    estoque_minimo: Mapped[int] = mapped_column(default=0, server_default="0")


class LoteMedicamento(Base):
    __tablename__ = "lotes_medicamentos"
    __table_args__ = (UniqueConstraint("medicamento_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    medicamento_id: Mapped[int] = mapped_column(ForeignKey("medicamentos.id"))
    codigo: Mapped[str] = mapped_column(String(80))
    validade: Mapped[date] = mapped_column(Date)
    quantidade: Mapped[int] = mapped_column(default=0, server_default="0")


class MovimentacaoEstoque(Base):
    __tablename__ = "movimentacoes_estoque"

    id: Mapped[int] = mapped_column(primary_key=True)
    medicamento_id: Mapped[int] = mapped_column(ForeignKey("medicamentos.id"))
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lotes_medicamentos.id", name="fk_movimentacoes_lote"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    tipo: Mapped[str] = mapped_column(String(10))
    quantidade: Mapped[int] = mapped_column()
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Convenio(Base):
    __tablename__ = "convenios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), unique=True)


class Cobranca(Base):
    __tablename__ = "cobrancas"

    id: Mapped[int] = mapped_column(primary_key=True)
    paciente_id: Mapped[int] = mapped_column(ForeignKey("pacientes.id"))
    convenio_id: Mapped[int | None] = mapped_column(ForeignKey("convenios.id"))
    descricao: Mapped[str] = mapped_column(String(500))
    valor_centavos: Mapped[int] = mapped_column(BigInteger)
    pago_centavos: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")

    @property
    def valor(self) -> Decimal:
        return Decimal(self.valor_centavos) / 100

    @property
    def valor_pago(self) -> Decimal:
        return Decimal(self.pago_centavos) / 100


class Pagamento(Base):
    __tablename__ = "pagamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cobranca_id: Mapped[int] = mapped_column(ForeignKey("cobrancas.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    valor_centavos: Mapped[int] = mapped_column(BigInteger)
    data_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def valor(self) -> Decimal:
        return Decimal(self.valor_centavos) / 100
