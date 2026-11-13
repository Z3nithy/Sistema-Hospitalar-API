import sqlite3
import sys
import os
import subprocess
from contextlib import closing

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import backup_sqlite
from backup_sqlite import copiar_banco
from database import get_db
from demonstracao import criar_demonstracao
from main import app


def test_backup_e_restauracao_nao_sobrescrevem_destino(tmp_path):
    origem = tmp_path / "origem.db"
    backup = tmp_path / "backup.db"
    restaurado = tmp_path / "restaurado.db"
    with closing(sqlite3.connect(origem)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE alembic_version (version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES ('teste')")
        db.execute("CREATE TABLE dados (valor TEXT)")
        db.execute("INSERT INTO dados VALUES ('antes')")
        db.commit()
        copiar_banco(origem, backup)
        db.execute("INSERT INTO dados VALUES ('depois')")
        db.commit()
    copiar_banco(backup, restaurado)
    with closing(sqlite3.connect(restaurado)) as copia:
        assert copia.execute("SELECT valor FROM dados").fetchall() == [("antes",)]
        assert copia.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(FileExistsError):
        copiar_banco(origem, restaurado)
    with pytest.raises(ValueError):
        copiar_banco(origem, origem)
    with pytest.raises(ValueError):
        copiar_banco(tmp_path / "ausente.db", tmp_path / "saida.db")
    invalido = tmp_path / "invalido.db"
    invalido.write_bytes(b"nao e um banco sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        copiar_banco(invalido, tmp_path / "copia-invalida.db")
    assert not (tmp_path / "copia-invalida.db").exists()


def test_comandos_backup_e_restauracao(tmp_path, monkeypatch):
    origem = tmp_path / "origem.db"
    backup = tmp_path / "backup.db"
    restaurado = tmp_path / "restaurado.db"
    with closing(sqlite3.connect(origem)) as db:
        db.execute("CREATE TABLE alembic_version (version_num TEXT)")
        db.execute("INSERT INTO alembic_version VALUES ('teste')")
        db.commit()
    monkeypatch.setattr(backup_sqlite.settings, "database_url", f"sqlite:///{origem.as_posix()}")
    monkeypatch.setattr(sys, "argv", ["backup_sqlite.py", "backup", "--destino", str(backup)])
    backup_sqlite.main()
    monkeypatch.setattr(sys, "argv", ["backup_sqlite.py", "restaurar", "--origem", str(backup), "--destino", str(restaurado)])
    backup_sqlite.main()
    with closing(sqlite3.connect(restaurado)) as copia:
        assert copia.execute("SELECT version_num FROM alembic_version").fetchone() == ("teste",)


def test_demonstracao_cria_banco_novo_sem_sobrescrever(tmp_path):
    destino = tmp_path / "demo.db"
    criar_demonstracao(destino, "senha-ficticia-de-teste")
    with closing(sqlite3.connect(destino)) as db:
        assert db.execute("SELECT login FROM usuarios").fetchone() == ("demo-admin",)
        assert db.execute("SELECT quantidade, quantidade_nao_rastreada FROM medicamentos").fetchone() == (5, 0)
        assert db.execute("SELECT COUNT(*) FROM auditoria").fetchone() == (6,)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    with pytest.raises(FileExistsError):
        criar_demonstracao(destino, "outra-senha-ficticia")


def test_sqlite_wal_e_timeout_configurados(tmp_path):
    env = os.environ.copy()
    env["SECRET_KEY"] = "test-secret-key-with-at-least-32-characters"
    env["DATABASE_URL"] = f"sqlite:///{(tmp_path / 'wal.db').as_posix()}"
    env["SQLITE_WAL"] = "true"
    env["SQLITE_BUSY_TIMEOUT_MS"] = "1234"
    codigo = (
        "from database.db import engine; "
        "c=engine.connect(); "
        "print(c.exec_driver_sql('PRAGMA journal_mode').scalar_one()); "
        "print(c.exec_driver_sql('PRAGMA busy_timeout').scalar_one()); "
        "print(c.exec_driver_sql('PRAGMA foreign_keys').scalar_one()); "
        "c.close(); engine.dispose()"
    )
    resultado = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, timeout=30)
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.splitlines() == ["wal", "1234", "1"]


def test_fluxo_documentado_de_demonstracao(tmp_path):
    destino = tmp_path / "fluxo.db"
    criar_demonstracao(destino, "senha-ficticia-de-teste")
    engine = create_engine(f"sqlite:///{destino.as_posix()}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def chaves_estrangeiras(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    fabrica = sessionmaker(bind=engine)

    def banco():
        with fabrica() as db:
            yield db

    app.dependency_overrides[get_db] = banco
    try:
        with TestClient(app) as client:
            login = client.post("/auth/login", json={"login": "demo-admin", "senha": "senha-ficticia-de-teste"})
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            janela = client.get("/disponibilidades", headers=headers).json()[0]
            evento = {"paciente_id": 1, "profissional_id": 1, "data_hora": janela["inicio"]}
            assert client.post("/consultas", headers=headers, json={**evento, "motivo": "Ficticio"}).status_code == 201
            assert client.post("/alergias", headers=headers, json={**evento, "agente": "Ficticio", "reacao": "Ficticia", "gravidade": "desconhecida"}).status_code == 201
            prescricao = client.post("/prescricoes", headers=headers, json={
                **evento, "medicamento": "Medicamento ficticio", "medicamento_id": 1, "orientacoes": "Ficticio",
            })
            assert prescricao.status_code == 201
            dados = {
                "prescricao_id": prescricao.json()["id"], "profissional_id": 1, "lote_id": 1,
                "idempotencia": "11111111-1111-4111-8111-111111111111", "data_hora": janela["inicio"],
                "quantidade": 1, "dose": "Ficticia", "via": "Ficticia",
            }
            assert client.post("/administracoes", headers=headers, json=dados).status_code == 201
            assert client.post("/administracoes", headers=headers, json=dados).status_code == 200
            assert client.get("/medicamentos/1", headers=headers).json()["quantidade"] == 4
            historico = client.get("/pacientes/1/historico", headers=headers).json()
            assert len(historico["administracoes"]) == 1
            assert len(historico["alergias"]) == 1
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
