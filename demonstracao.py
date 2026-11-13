import argparse
from datetime import date, datetime, time, timedelta, timezone
from getpass import getpass
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from core.config import settings
from core.senha_hash import criar_hash_senha
from models import Disponibilidade, LoteMedicamento, Medicamento, MovimentacaoEstoque, Paciente, Profissional, User, VinculoPaciente
from schemas.hospital import UsuarioCriar
from services.hospital import auditar


def criar_demonstracao(destino: Path, senha: str) -> None:
    dados = UsuarioCriar(nome="Administrador demonstracao", login="demo-admin", senha=senha, perfil="admin")
    destino = destino.resolve()
    fd = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    url = URL.create("sqlite", database=destino.as_posix()).render_as_string(hide_password=False)
    anterior = settings.database_url
    settings.database_url = url
    engine = None
    try:
        raiz = Path(__file__).resolve().parent
        config = Config(str(raiz / "alembic.ini"))
        config.set_main_option("script_location", str(raiz / "migrations"))
        command.upgrade(config, "head")
        engine = create_engine(url)

        @event.listens_for(engine, "connect")
        def chaves_estrangeiras(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        with Session(engine) as db:
            usuario = User(nome=dados.nome, login=dados.login, senha_hash=criar_hash_senha(dados.senha), perfil="admin")
            paciente = Paciente(nome="Paciente ficticio", documento="DEMO-001", nascimento=date(1990, 1, 1))
            profissional = Profissional(nome="Profissional ficticio", registro="DEMO-CRM-001", especialidade="Clinica")
            medicamento = Medicamento(nome="Medicamento ficticio", quantidade=5, estoque_minimo=1)
            db.add_all([usuario, paciente, profissional, medicamento])
            db.flush()
            hoje = datetime.now(timezone.utc).date()
            inicio = datetime.combine(hoje + timedelta(days=1), time(9), tzinfo=timezone.utc)
            disponibilidade = Disponibilidade(profissional_id=profissional.id, inicio=inicio, fim=inicio + timedelta(hours=4))
            lote = LoteMedicamento(medicamento_id=medicamento.id, codigo="DEMO-LOTE-001", validade=hoje + timedelta(days=365), quantidade=5)
            vinculo = VinculoPaciente(paciente_id=paciente.id, profissional_id=profissional.id)
            db.add_all([disponibilidade, lote, vinculo])
            db.flush()
            db.add(MovimentacaoEstoque(
                medicamento_id=medicamento.id, lote_id=lote.id, usuario_id=usuario.id,
                tipo="entrada", quantidade=5, data_hora=datetime.now(timezone.utc),
            ))
            for objeto in (paciente, profissional, medicamento, disponibilidade, lote, vinculo):
                auditar(db, usuario, "criar", objeto)
            db.commit()
    finally:
        if engine is not None:
            engine.dispose()
        settings.database_url = anterior


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria um banco novo apenas com dados ficticios.")
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    senha = getpass("Senha do administrador de demonstracao: ")
    if senha != getpass("Confirme a senha: "):
        raise SystemExit("As senhas nao conferem.")
    criar_demonstracao(args.database, senha)
    print("Banco de demonstracao criado. Login: demo-admin")


if __name__ == "__main__":
    main()
