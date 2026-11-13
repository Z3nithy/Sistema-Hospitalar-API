from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import sys
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from core.config import settings
from core.senha_hash import criar_hash_senha
from database import get_db
from dependencies.autenticacao import OPERACOES_RECURSOS
from main import app
from models import User
import redefinir_senha


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'hospital.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        db.add(User(nome="Administrador", login="admin", senha_hash=criar_hash_senha("senha-segura"), perfil="admin"))
        db.commit()

    def banco():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = banco
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def autenticar(client, login="admin", senha="senha-segura"):
    response = client.post("/auth/login", json={"login": login, "senha": senha})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def criar(client, headers, caminho, dados):
    response = client.post(caminho, headers=headers, json=dados)
    assert response.status_code == 201, response.text
    return response.json()


def test_autenticacao_e_permissoes(client):
    assert client.post("/auth/login", json={"login": "admin", "senha": "errada"}).status_code == 401
    assert client.get("/pacientes").status_code in (401, 403)
    admin = autenticar(client)
    usuario = criar(client, admin, "/usuarios", {
        "nome": "Recepcao", "login": "recepcao", "senha": "outra-senha", "perfil": "recepcao",
    })
    assert "senha_hash" not in usuario
    recepcao = autenticar(client, "recepcao", "outra-senha")
    assert client.get("/auth/me", headers=recepcao).json()["perfil"] == "recepcao"
    assert client.get("/prontuarios", headers=recepcao).status_code == 403
    assert client.post("/usuarios", headers=recepcao, json={}).status_code == 403
    assert client.get("/pacientes", headers={"Authorization": "Bearer invalido"}).status_code == 401


def test_fluxos_hospitalares_e_conflitos(client):
    headers = autenticar(client)
    paciente = criar(client, headers, "/pacientes", {
        "nome": "Paciente", "documento": "123", "nascimento": "1990-01-01",
    })
    outro = criar(client, headers, "/pacientes", {
        "nome": "Outro", "documento": "456", "nascimento": "2000-01-01",
    })
    profissional = criar(client, headers, "/profissionais", {
        "nome": "Profissional", "registro": "CRM-1", "especialidade": "Clinica",
    })
    criar(client, headers, "/disponibilidades", {
        "profissional_id": profissional["id"],
        "inicio": "2026-01-01T12:00:00Z", "fim": "2026-01-01T16:00:00Z",
    })
    leito = criar(client, headers, "/leitos", {"codigo": "A1", "setor": "Clinica"})
    assert client.post("/pacientes", headers=headers, json={
        "nome": "Duplicado", "documento": "123", "nascimento": "1990-01-01",
    }).status_code == 409

    evento = {"paciente_id": paciente["id"], "profissional_id": profissional["id"], "data_hora": "2026-01-01T10:00:00-03:00"}
    consulta = criar(client, headers, "/consultas", {**evento, "motivo": "Retorno"})
    assert datetime.fromisoformat(consulta["data_hora"]).hour == 13
    assert client.post("/consultas", headers=headers, json={**evento, "data_hora": "2026-01-01T13:00:00Z", "motivo": "Outro"}).status_code == 409
    assert client.post(f"/consultas/{consulta['id']}/cancelar", headers=headers).status_code == 200
    criar(client, headers, "/consultas", {**evento, "motivo": "Retorno"})
    assert client.post("/consultas", headers=headers, json={**evento, "data_hora": "2026-01-01T13:00:00", "motivo": "Sem fuso"}).status_code == 422
    assert client.post("/consultas", headers=headers, json={**evento, "paciente_id": 999, "motivo": "Invalido"}).status_code == 404

    internacao = criar(client, headers, "/internacoes", {"paciente_id": paciente["id"], "leito_id": leito["id"], "profissional_id": profissional["id"]})
    assert client.post("/internacoes", headers=headers, json={"paciente_id": outro["id"], "leito_id": leito["id"], "profissional_id": profissional["id"]}).status_code == 409
    segundo_leito = criar(client, headers, "/leitos", {"codigo": "A2", "setor": "Clinica"})
    assert client.post("/internacoes", headers=headers, json={"paciente_id": paciente["id"], "leito_id": segundo_leito["id"], "profissional_id": profissional["id"]}).status_code == 409
    assert client.post(f"/internacoes/{internacao['id']}/alta", headers=headers).status_code == 200
    assert client.post(f"/internacoes/{internacao['id']}/alta", headers=headers).status_code == 409
    criar(client, headers, "/internacoes", {"paciente_id": outro["id"], "leito_id": leito["id"], "profissional_id": profissional["id"]})

    criar(client, headers, "/prontuarios", {**evento, "descricao": "Evolucao"})
    criar(client, headers, "/prescricoes", {**evento, "medicamento": "Medicamento ficticio", "orientacoes": "Orientacao ficticia"})
    exame = criar(client, headers, "/exames", {**evento, "tipo": "Exame ficticio"})
    resultado = client.put(f"/exames/{exame['id']}/resultado", headers=headers, json={"resultado": "Resultado ficticio"})
    assert resultado.status_code == 200
    assert resultado.json()["resultado"] == "Resultado ficticio"
    assert len(client.get("/prontuarios", headers=headers).json()) == 1
    assert client.get("/pacientes", headers=headers, params={"limit": 1}).json() == [paciente]
    assert client.put(f"/pacientes/{paciente['id']}", headers=headers, json={
        "nome": "Paciente atualizado", "documento": "123", "nascimento": "1990-01-01",
    }).json()["nome"] == "Paciente atualizado"


def test_acesso_vinculos_auditoria_e_historico(client):
    admin = autenticar(client)
    paciente = criar(client, admin, "/pacientes", {"nome": "Alvo", "documento": "10", "nascimento": "1990-01-01"})
    outro = criar(client, admin, "/pacientes", {"nome": "Outro", "documento": "11", "nascimento": "1990-01-01"})
    profissional = criar(client, admin, "/profissionais", {"nome": "Medico", "registro": "M1", "especialidade": "Clinica"})
    outro_profissional = criar(client, admin, "/profissionais", {"nome": "Outro", "registro": "M2", "especialidade": "Clinica"})
    usuario = criar(client, admin, "/usuarios", {"nome": "Medico", "login": "medico", "senha": "senha-medico", "perfil": "medico"})
    medico = autenticar(client, "medico", "senha-medico")
    assert client.get(f"/pacientes/{paciente['id']}", headers=medico).status_code == 403
    assert client.get("/pacientes", headers=medico).json() == []
    assert client.put(f"/usuarios/{usuario['id']}/profissional", headers=admin, json={"profissional_id": profissional["id"]}).status_code == 200
    criar(client, admin, "/disponibilidades", {"profissional_id": profissional["id"], "inicio": "2026-01-01T09:00:00Z", "fim": "2026-01-01T12:00:00Z"})
    criar(client, admin, "/consultas", {"paciente_id": paciente["id"], "profissional_id": profissional["id"], "data_hora": "2026-01-01T10:00:00Z", "motivo": "Retorno"})
    assert [item["id"] for item in client.get("/pacientes", headers=medico).json()] == [paciente["id"]]
    evento = {"paciente_id": paciente["id"], "profissional_id": profissional["id"], "data_hora": "2026-01-01T10:00:00Z"}
    prontuario = criar(client, medico, "/prontuarios", {**evento, "descricao": "Texto sensivel ficticio"})
    assert client.post("/prontuarios", headers=medico, json={**evento, "paciente_id": outro["id"], "descricao": "Nao permitido"}).status_code == 403
    assert client.post("/prontuarios", headers=medico, json={**evento, "profissional_id": outro_profissional["id"], "descricao": "Nao permitido"}).status_code == 403
    exame = criar(client, medico, "/exames", {**evento, "tipo": "Teste"})
    assert client.put(f"/exames/{exame['id']}/resultado", headers=medico, json={"resultado": "Resultado ficticio"}).status_code == 200
    historico = client.get(f"/pacientes/{paciente['id']}/historico", headers=medico)
    assert historico.status_code == 200
    assert historico.json()["prontuarios"][0]["id"] == prontuario["id"]
    permissao = f"/usuarios/{usuario['id']}/permissoes/listar_prontuarios"
    assert client.put(permissao, headers=admin, json={"permitida": False}).status_code == 200
    assert client.get(f"/pacientes/{paciente['id']}/historico", headers=medico).status_code == 403
    assert client.put(permissao, headers=admin, json={"permitida": True}).status_code == 200
    assert client.get(f"/pacientes/{outro['id']}/historico", headers=medico).status_code == 403
    auditoria = client.get("/auditoria", headers=admin, params={"recurso": "exames", "registro_id": exame["id"]}).json()
    assert {item["acao"] for item in auditoria} == {"criar", "alterar", "leitura"}
    assert all(item["usuario_id"] == usuario["id"] for item in auditoria)
    assert "Resultado ficticio" not in str(auditoria)
    assert client.get("/auditoria", headers=medico).status_code == 403
    vinculo = client.get("/vinculos", headers=admin, params={"paciente_id": paciente["id"]}).json()[0]
    assert client.delete(f"/vinculos/{vinculo['id']}", headers=admin).status_code == 204
    assert client.get(f"/prontuarios/{prontuario['id']}", headers=medico).status_code == 403


def test_agenda_duracao_disponibilidade_e_conclusao(client):
    admin = autenticar(client)
    paciente = criar(client, admin, "/pacientes", {"nome": "Paciente", "documento": "20", "nascimento": "1990-01-01"})
    profissional = criar(client, admin, "/profissionais", {"nome": "Medico", "registro": "M3", "especialidade": "Clinica"})
    dados = {"paciente_id": paciente["id"], "profissional_id": profissional["id"], "data_hora": "2026-02-01T10:00:00Z", "duracao_minutos": 60, "motivo": "Consulta"}
    assert client.post("/consultas", headers=admin, json=dados).status_code == 409
    janela = criar(client, admin, "/disponibilidades", {"profissional_id": profissional["id"], "inicio": "2026-02-01T10:00:00Z", "fim": "2026-02-01T12:00:00Z"})
    consulta = criar(client, admin, "/consultas", dados)
    assert client.delete(f"/disponibilidades/{janela['id']}", headers=admin).status_code == 409
    assert client.post("/consultas", headers=admin, json={**dados, "data_hora": "2026-02-01T10:30:00Z"}).status_code == 409
    assert client.post("/consultas", headers=admin, json={**dados, "data_hora": "2026-02-01T11:30:00Z"}).status_code == 409
    proxima = criar(client, admin, "/consultas", {**dados, "data_hora": "2026-02-01T11:00:00Z"})
    assert client.post(f"/consultas/{consulta['id']}/concluir", headers=admin).json()["status"] == "concluida"
    assert client.post(f"/consultas/{consulta['id']}/cancelar", headers=admin).status_code == 409
    assert client.post(f"/consultas/{proxima['id']}/cancelar", headers=admin).status_code == 200
    criar(client, admin, "/consultas", {**dados, "data_hora": "2026-02-01T11:00:00Z"})
    lista = client.get("/consultas", headers=admin, params={"paciente_id": paciente["id"], "desde": "2026-02-01T11:00:00Z"}).json()
    assert len(lista) == 2


def test_estoque_cobrancas_e_pagamentos(client):
    admin = autenticar(client)
    paciente = criar(client, admin, "/pacientes", {"nome": "Paciente", "documento": "30", "nascimento": "1990-01-01"})
    medicamento = criar(client, admin, "/medicamentos", {"nome": "Medicamento ficticio"})
    lote = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "L1", "validade": "2099-12-31"})
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "entrada", "quantidade": 5})
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "saida", "quantidade": 2})
    assert client.post("/estoque/movimentacoes", headers=admin, json={"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "saida", "quantidade": 4}).status_code == 409
    assert client.get("/medicamentos", headers=admin).json()[0]["quantidade"] == 3
    assert len(client.get("/estoque/movimentacoes", headers=admin).json()) == 2
    convenio = criar(client, admin, "/convenios", {"nome": "Convenio ficticio"})
    cobranca = criar(client, admin, "/cobrancas", {"paciente_id": paciente["id"], "convenio_id": convenio["id"], "descricao": "Servico", "valor": "0.30"})
    criar(client, admin, f"/cobrancas/{cobranca['id']}/pagamentos", {"valor": "0.10"})
    criar(client, admin, f"/cobrancas/{cobranca['id']}/pagamentos", {"valor": "0.20"})
    assert client.post(f"/cobrancas/{cobranca['id']}/pagamentos", headers=admin, json={"valor": "0.01"}).status_code == 409
    assert client.get("/cobrancas", headers=admin).json()[0]["valor_pago"] == "0.3"
    assert len(client.get(f"/cobrancas/{cobranca['id']}/pagamentos", headers=admin).json()) == 2


def test_operacoes_concorrentes_nao_causam_sobreposicao_ou_saldo_negativo(client):
    admin = autenticar(client)
    paciente = criar(client, admin, "/pacientes", {"nome": "Paciente", "documento": "40", "nascimento": "1990-01-01"})
    profissional = criar(client, admin, "/profissionais", {"nome": "Medico", "registro": "M4", "especialidade": "Clinica"})
    criar(client, admin, "/disponibilidades", {"profissional_id": profissional["id"], "inicio": "2026-02-01T10:00:00Z", "fim": "2026-02-01T12:00:00Z"})
    dados = {"paciente_id": paciente["id"], "profissional_id": profissional["id"], "duracao_minutos": 60, "motivo": "Consulta"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(
            lambda horario: client.post("/consultas", headers=admin, json={**dados, "data_hora": horario}).status_code,
            ["2026-02-01T10:00:00Z", "2026-02-01T10:30:00Z"],
        ))
    assert sorted(respostas) == [201, 409]
    medicamento = criar(client, admin, "/medicamentos", {"nome": "Teste concorrencia"})
    lote = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "L1", "validade": "2099-12-31"})
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "entrada", "quantidade": 1})
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(
            lambda _: client.post("/estoque/movimentacoes", headers=admin, json={"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "saida", "quantidade": 1}).status_code,
            range(2),
        ))
    assert sorted(respostas) == [201, 409]
    cobranca = criar(client, admin, "/cobrancas", {"paciente_id": paciente["id"], "descricao": "Servico", "valor": "1.00"})
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(
            lambda _: client.post(f"/cobrancas/{cobranca['id']}/pagamentos", headers=admin, json={"valor": "1.00"}).status_code,
            range(2),
        ))
    assert sorted(respostas) == [201, 409]


def test_migracao_preserva_dados_anteriores(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'antigo.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config("alembic.ini")
    command.upgrade(config, "8b5d35c446d0")
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO pacientes (id, nome, documento, nascimento) VALUES (1, 'Existente', '101', '1990-01-01')"))
        conn.execute(text("INSERT INTO profissionais (id, nome, registro, especialidade) VALUES (1, 'Profissional', '123', 'Clinica')"))
        conn.execute(text("INSERT INTO usuarios (id, nome, login, senha_hash, perfil, ativo) VALUES (1, 'Usuario', 'existente', 'hash', 'medico', 1)"))
        conn.execute(text("INSERT INTO leitos (id, codigo, setor) VALUES (1, 'L1', 'Clinica')"))
        conn.execute(text("INSERT INTO internacoes (id, paciente_id, leito_id, entrada, paciente_ativo_id, leito_ativo_id) VALUES (1, 1, 1, '2026-01-01 10:00:00', 1, 1)"))
        conn.execute(text("INSERT INTO consultas (id, paciente_id, profissional_id, data_hora, horario_ativo, motivo, status) VALUES (1, 1, 1, '2026-01-01 10:00:00', '2026-01-01 10:00:00', 'Retorno', 'agendada')"))
    command.upgrade(config, "f1b3debaa233")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO medicamentos (id, nome, quantidade) VALUES (1, 'Legado', 7)"))
        conn.execute(text("INSERT INTO convenios (id, nome) VALUES (1, 'Convenio legado')"))
        conn.execute(text("INSERT INTO cobrancas (id, paciente_id, convenio_id, descricao, valor_centavos, pago_centavos) VALUES (1, 1, 1, 'Legado', 1000, 300)"))
        conn.execute(text("INSERT INTO movimentacoes_estoque (id, medicamento_id, usuario_id, tipo, quantidade, data_hora) VALUES (1, 1, 1, 'entrada', 7, '2026-01-01 10:00:00')"))
        conn.execute(text("INSERT INTO prescricoes (id, paciente_id, profissional_id, data_hora, medicamento, orientacoes) VALUES (1, 1, 1, '2026-01-01 10:00:00', 'Legado', 'Informacao ficticia')"))
    command.upgrade(config, "head")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT nome FROM pacientes WHERE id=1")).scalar_one() == "Existente"
        assert conn.execute(text("SELECT duracao_minutos FROM consultas WHERE id=1")).scalar_one() == 30
        assert conn.execute(text("SELECT COUNT(*) FROM vinculos_pacientes")).scalar_one() == 0
        assert conn.execute(text("SELECT profissional_id FROM usuarios WHERE id=1")).scalar_one() is None
        assert conn.execute(text("SELECT profissional_id FROM internacoes WHERE id=1")).scalar_one() is None
        assert conn.execute(text("SELECT quantidade_nao_rastreada FROM medicamentos WHERE id=1")).scalar_one() == 7
        assert conn.execute(text("SELECT lote_id FROM movimentacoes_estoque WHERE id=1")).scalar_one() is None
        assert conn.execute(text("SELECT medicamento_id FROM prescricoes WHERE id=1")).scalar_one() is None
        assert conn.execute(text("SELECT convenio_id, valor_centavos, pago_centavos FROM cobrancas WHERE id=1")).one() == (1, 1000, 300)
        assert conn.execute(text("PRAGMA foreign_key_check")).all() == []
    command.downgrade(config, "8b5d35c446d0")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT motivo FROM consultas WHERE id=1")).scalar_one() == "Retorno"
        assert conn.execute(text("SELECT paciente_ativo_id FROM internacoes WHERE id=1")).scalar_one() == 1
    engine.dispose()


def test_sessoes_redefinicao_senha_e_eventos_sem_dados_sensiveis(client, monkeypatch):
    admin = autenticar(client)
    criar(client, admin, "/usuarios", {"nome": "Recepcao", "login": "recepcao", "senha": "senha-segura-1", "perfil": "recepcao"})
    primeiro = autenticar(client, "recepcao", "senha-segura-1")
    segundo = autenticar(client, "recepcao", "senha-segura-1")
    assert client.post("/auth/logout", headers=primeiro).status_code == 204
    assert client.get("/auth/me", headers=segundo).status_code == 401
    terceiro = autenticar(client, "recepcao", "senha-segura-1")
    with closing(app.dependency_overrides[get_db]()) as gerador:
        db = next(gerador)
        fabrica = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr(redefinir_senha, "SessionLocal", fabrica)
    monkeypatch.setattr(redefinir_senha, "getpass", lambda _: "senha-nova-2")
    monkeypatch.setattr(sys, "argv", ["redefinir_senha.py", "--login", "recepcao"])
    redefinir_senha.main()
    assert client.get("/auth/me", headers=terceiro).status_code == 401
    assert client.post("/auth/login", json={"login": "recepcao", "senha": "senha-segura-1"}).status_code == 401
    novo = autenticar(client, "recepcao", "senha-nova-2")
    negado = client.get("/auditoria?dado=texto-sensivel", headers=novo)
    assert negado.status_code == 403
    assert negado.headers["cache-control"] == "no-store"
    eventos = client.get("/eventos-seguranca", headers=admin).json()
    assert {"sessoes_revogadas", "senha_redefinida_local", "acesso_negado"} <= {item["evento"] for item in eventos}
    assert any(item["evento"] == "acesso_negado" and item["usuario_id"] is not None for item in eventos)
    assert "senha" not in str([item["operacao"] for item in eventos if item["evento"] == "acesso_negado"])
    assert "texto-sensivel" not in str(eventos)
    assert "senha-nova-2" not in str(eventos)


def test_permissoes_por_operacao_respeitam_perfis(client):
    admin = autenticar(client)
    usuario = criar(client, admin, "/usuarios", {"nome": "Recepcao", "login": "recepcao", "senha": "senha-segura-1", "perfil": "recepcao"})
    recepcao = autenticar(client, "recepcao", "senha-segura-1")
    operacoes = client.get("/operacoes", headers=admin).json()
    assert "listar_pacientes" in {item["operacao"] for item in operacoes}
    assert client.get("/pacientes", headers=recepcao).status_code == 200
    rota = f"/usuarios/{usuario['id']}/permissoes/listar_pacientes"
    assert client.put(rota, headers=admin, json={"permitida": False}).status_code == 200
    assert client.get("/pacientes", headers=recepcao).status_code == 403
    assert client.get("/profissionais", headers=recepcao).status_code == 200
    assert client.get(f"/usuarios/{usuario['id']}/permissoes", headers=admin).json()["restricoes"] == ["listar_pacientes"]
    assert client.put(rota, headers=admin, json={"permitida": True}).status_code == 200
    assert client.get("/pacientes", headers=recepcao).status_code == 200
    assert client.put(f"/usuarios/{usuario['id']}/permissoes/listar_usuarios", headers=admin, json={"permitida": True}).status_code == 200
    assert client.get("/usuarios", headers=recepcao).status_code == 403
    assert client.put("/usuarios/1/permissoes/listar_pacientes", headers=admin, json={"permitida": False}).status_code == 403
    assert client.put(f"/usuarios/{usuario['id']}/permissoes/inexistente", headers=admin, json={"permitida": False}).status_code == 404


def test_lotes_validade_regularizacao_e_alertas(client):
    admin = autenticar(client)
    medicamento = criar(client, admin, "/medicamentos", {"nome": "Teste lote", "estoque_minimo": 3})
    with closing(app.dependency_overrides[get_db]()) as gerador:
        db = next(gerador)
        db.execute(text("UPDATE medicamentos SET quantidade = 5, quantidade_nao_rastreada = 5 WHERE id = :id"), {"id": medicamento["id"]})
        db.commit()
    valido = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "VALIDO", "validade": "2099-12-31"})
    vencido = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "VENCIDO", "validade": "2000-01-01"})
    assert client.get("/estoque/alertas", headers=admin).json()[0]["quantidade_disponivel"] == 0
    criar(client, admin, "/estoque/regularizacoes", {"lote_id": valido["id"], "quantidade": 2})
    criar(client, admin, "/estoque/regularizacoes", {"lote_id": vencido["id"], "quantidade": 2})
    assert client.post("/estoque/regularizacoes", headers=admin, json={"lote_id": valido["id"], "quantidade": 2}).status_code == 409
    assert client.post("/estoque/movimentacoes", headers=admin, json={"medicamento_id": medicamento["id"], "lote_id": vencido["id"], "tipo": "saida", "quantidade": 1}).status_code == 409
    assert client.get("/medicamentos", headers=admin).json()[0]["quantidade"] == 5
    assert client.get("/medicamentos", headers=admin).json()[0]["quantidade_nao_rastreada"] == 1
    assert client.get("/estoque/alertas", headers=admin).json()[0]["quantidade_disponivel"] == 2
    assert client.get("/monitoramento", headers=admin).json()["medicamentos_com_estoque_baixo"] == 1
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": vencido["id"], "tipo": "descarte", "quantidade": 2})
    assert client.get("/medicamentos", headers=admin).json()[0]["quantidade"] == 3
    assert client.post("/estoque/movimentacoes", headers=admin, json={"medicamento_id": medicamento["id"], "lote_id": valido["id"], "tipo": "saida", "quantidade": 3}).status_code == 409
    assert client.get("/medicamentos", headers=admin).json()[0]["quantidade"] == 3
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": valido["id"], "tipo": "entrada", "quantidade": 2})
    assert client.get("/estoque/alertas", headers=admin).json() == []
    assert client.get("/estoque/lotes", headers=admin, params={"vencido": True}).json()[0]["id"] == vencido["id"]
    assert client.post("/estoque/movimentacoes", headers=admin, json={"medicamento_id": medicamento["id"], "tipo": "saida", "quantidade": 1}).status_code == 422


def test_readiness_verifica_migracao(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    with closing(app.dependency_overrides[get_db]()) as gerador:
        db = next(gerador)
        db.execute(text("DROP TABLE alembic_version"))
        db.commit()
    assert client.get("/health/ready").status_code == 503


def preparar_fluxo_clinico(client):
    admin = autenticar(client)
    paciente = criar(client, admin, "/pacientes", {"nome": "Paciente ficticio", "documento": "77", "nascimento": "1990-01-01"})
    medico = criar(client, admin, "/profissionais", {"nome": "Medico ficticio", "registro": "M77", "especialidade": "Clinica"})
    enfermeiro = criar(client, admin, "/profissionais", {"nome": "Enfermagem ficticia", "registro": "E77", "especialidade": "Enfermagem"})
    conta = criar(client, admin, "/usuarios", {"nome": "Enfermagem", "login": "enfermagem", "senha": "senha-enfermagem", "perfil": "enfermagem"})
    assert client.put(f"/usuarios/{conta['id']}/profissional", headers=admin, json={"profissional_id": enfermeiro["id"]}).status_code == 200
    criar(client, admin, "/vinculos", {"profissional_id": enfermeiro["id"], "paciente_id": paciente["id"]})
    headers = autenticar(client, "enfermagem", "senha-enfermagem")
    medicamento = criar(client, admin, "/medicamentos", {"nome": "Medicamento ficticio"})
    lote = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "LOTE-77", "validade": "2099-12-31"})
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "entrada", "quantidade": 3})
    prescricao = criar(client, admin, "/prescricoes", {
        "paciente_id": paciente["id"], "profissional_id": medico["id"],
        "data_hora": "2026-01-01T10:00:00Z", "medicamento": "Medicamento ficticio",
        "medicamento_id": medicamento["id"], "orientacoes": "Informacao ficticia",
    })
    return admin, headers, paciente, medico, enfermeiro, conta, medicamento, lote, prescricao


def test_dados_clinicos_estruturados_e_bloqueio_por_recurso(client):
    admin, enfermagem, paciente, medico, enfermeiro, conta, _, _, _ = preparar_fluxo_clinico(client)
    evento = {"paciente_id": paciente["id"], "profissional_id": enfermeiro["id"], "data_hora": "2026-01-01T10:00:00Z"}
    alergia = criar(client, enfermagem, "/alergias", {**evento, "agente": "Ficticio", "reacao": "Ficticia", "gravidade": "desconhecida"})
    criar(client, enfermagem, "/evolucoes", {**evento, "subjetivo": "Ficticio", "objetivo": "Ficticio", "avaliacao": "Ficticia", "plano": "Ficticio"})
    diagnostico = criar(client, admin, "/diagnosticos", {**evento, "profissional_id": medico["id"], "codigo": "TESTE", "descricao": "Ficticio"})
    assert client.post("/diagnosticos", headers=enfermagem, json={**evento, "codigo": "TESTE", "descricao": "Ficticio"}).status_code == 403
    historico = client.get(f"/pacientes/{paciente['id']}/historico", headers=enfermagem).json()
    assert historico["alergias"][0]["id"] == alergia["id"]
    assert historico["diagnosticos"][0]["id"] == diagnostico["id"]
    assert len(historico["evolucoes"]) == 1
    recurso = f"/usuarios/{conta['id']}/recursos/alergias"
    assert client.put(recurso, headers=admin, json={"permitida": False}).status_code == 200
    eventos = client.get("/eventos-seguranca", headers=admin).json()
    assert any(evento["evento"] == "recurso_bloqueado" and evento["operacao"] == "alergias" and evento["alvo_usuario_id"] == conta["id"] for evento in eventos)
    assert client.get("/alergias", headers=enfermagem).status_code == 403
    assert client.get(f"/alergias/{alergia['id']}", headers=enfermagem).status_code == 403
    assert client.get(f"/pacientes/{paciente['id']}/historico", headers=enfermagem).status_code == 403
    assert client.get("/diagnosticos", headers=enfermagem).status_code == 200
    assert "alergias" in client.get(f"/usuarios/{conta['id']}/recursos", headers=admin).json()["restritos"]
    assert client.put(recurso, headers=admin, json={"permitida": True}).status_code == 200
    assert client.get(f"/pacientes/{paciente['id']}/historico", headers=enfermagem).status_code == 200


def test_administracao_atomica_idempotente_e_autorizada(client):
    admin, enfermagem, paciente, medico, enfermeiro, conta, medicamento, lote, prescricao = preparar_fluxo_clinico(client)
    dados = {
        "prescricao_id": prescricao["id"], "profissional_id": enfermeiro["id"],
        "lote_id": lote["id"], "idempotencia": "11111111-1111-4111-8111-111111111111",
        "data_hora": "2026-01-01T10:00:00Z", "quantidade": 1, "dose": "Ficticia", "via": "Ficticia",
    }
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda _: client.post("/administracoes", headers=enfermagem, json=dados), range(2)))
    assert sorted(resposta.status_code for resposta in respostas) == [200, 201]
    assert respostas[0].json()["id"] == respostas[1].json()["id"]
    assert client.get(f"/medicamentos/{medicamento['id']}", headers=admin).json()["quantidade"] == 2
    assert len(client.get("/estoque/movimentacoes", headers=admin).json()) == 2
    assert client.post("/administracoes", headers=enfermagem, json={**dados, "quantidade": 2}).status_code == 409
    assert client.post("/administracoes", headers=enfermagem, json={
        **dados, "idempotencia": "22222222-2222-4222-8222-222222222222", "quantidade": 3,
    }).status_code == 409
    assert client.get(f"/medicamentos/{medicamento['id']}", headers=admin).json()["quantidade"] == 2
    assert len(client.get("/administracoes", headers=enfermagem).json()) == 1
    outro = criar(client, admin, "/medicamentos", {"nome": "Outro medicamento ficticio"})
    lote_errado = criar(client, admin, "/estoque/lotes", {"medicamento_id": outro["id"], "codigo": "OUTRO", "validade": "2099-12-31"})
    assert client.post("/administracoes", headers=enfermagem, json={
        **dados, "idempotencia": "33333333-3333-4333-8333-333333333333", "lote_id": lote_errado["id"],
    }).status_code == 422
    vencido = criar(client, admin, "/estoque/lotes", {"medicamento_id": medicamento["id"], "codigo": "VENCIDO", "validade": "2000-01-01"})
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": vencido["id"], "tipo": "entrada", "quantidade": 1})
    assert client.post("/administracoes", headers=enfermagem, json={
        **dados, "idempotencia": "44444444-4444-4444-8444-444444444444", "lote_id": vencido["id"],
    }).status_code == 409
    criar(client, admin, "/estoque/movimentacoes", {"medicamento_id": medicamento["id"], "lote_id": lote["id"], "tipo": "entrada", "quantidade": 1})
    assert client.post("/administracoes", headers=enfermagem, json={
        **dados, "idempotencia": "22222222-2222-4222-8222-222222222222", "quantidade": 3,
    }).status_code == 201
    assert client.get(f"/medicamentos/{medicamento['id']}", headers=admin).json()["quantidade"] == 1
    assert client.get(f"/pacientes/{paciente['id']}/historico", headers=enfermagem).json()["administracoes"][0]["id"] == respostas[0].json()["id"]
    assert client.put(f"/usuarios/{conta['id']}/recursos/prescricoes", headers=admin, json={"permitida": False}).status_code == 200
    assert client.get("/administracoes", headers=enfermagem).status_code == 403
    assert client.get(f"/administracoes/{respostas[0].json()['id']}", headers=enfermagem).status_code == 403
    assert client.post("/administracoes", headers=enfermagem, json=dados).status_code == 403
    assert client.get(f"/medicamentos/{medicamento['id']}", headers=admin).json()["quantidade"] == 1


def test_limite_login_por_ip_e_expiracao(client):
    for _ in range(5):
        assert client.post("/auth/login", json={"login": "inexistente", "senha": "errada"}).status_code == 401
    bloqueado = client.post("/auth/login", headers={"X-Forwarded-For": "203.0.113.10"}, json={"login": "admin", "senha": "senha-segura"})
    assert bloqueado.status_code == 429
    assert 1 <= int(bloqueado.headers["retry-after"]) <= 900
    with closing(app.dependency_overrides[get_db]()) as gerador:
        db = next(gerador)
        registro = db.execute(text("SELECT identificador, tentativas FROM limites_login")).one()
        assert len(registro.identificador) == 64
        assert "testclient" not in registro.identificador
        assert registro.tentativas == 5
        db.execute(text("UPDATE limites_login SET inicio = 0, bloqueado_ate = 0"))
        db.commit()
    admin = autenticar(client)
    eventos = client.get("/eventos-seguranca", headers=admin).json()
    assert any(evento["evento"] == "limite_login" for evento in eventos)


def test_limite_login_compartilhado_em_tentativas_concorrentes(client):
    with ThreadPoolExecutor(max_workers=8) as executor:
        respostas = list(executor.map(
            lambda _: client.post("/auth/login", json={"login": "inexistente", "senha": "errada"}).status_code,
            range(8),
        ))
    assert respostas.count(401) == 5
    assert respostas.count(429) == 3


def test_login_bem_sucedido_limpa_falhas_antes_do_bloqueio(client):
    for _ in range(4):
        assert client.post("/auth/login", json={"login": "inexistente", "senha": "errada"}).status_code == 401
    autenticar(client)
    for _ in range(5):
        assert client.post("/auth/login", json={"login": "inexistente", "senha": "errada"}).status_code == 401
    assert client.post("/auth/login", json={"login": "admin", "senha": "senha-segura"}).status_code == 429


def test_rotas_clinicas_possuem_bloqueios_de_recurso():
    rotas = (
        ("/pacientes", ("pacientes",)),
        ("/consultas", ("pacientes", "consultas")),
        ("/internacoes", ("pacientes", "internacoes")),
        ("/prontuarios", ("pacientes", "prontuarios")),
        ("/prescricoes", ("pacientes", "prescricoes")),
        ("/exames", ("pacientes", "exames")),
        ("/alergias", ("pacientes", "alergias")),
        ("/diagnosticos", ("pacientes", "diagnosticos")),
        ("/evolucoes", ("pacientes", "evolucoes")),
        ("/administracoes", ("pacientes", "prescricoes", "administracoes")),
        ("/cobrancas", ("pacientes",)),
        ("/carteirinhas", ("pacientes", "convenios")),
        ("/autorizacoes-convenio", ("pacientes", "convenios")),
        ("/guias-convenio", ("pacientes", "convenios")),
        ("/planos", ("convenios",)),
        ("/procedimentos", ("convenios",)),
        ("/coberturas", ("convenios",)),
    )
    for router in app.state.routers_permissoes:
        for rota in router.routes:
            if not isinstance(rota, APIRoute):
                continue
            for prefixo, recursos in rotas:
                if rota.path == prefixo or rota.path.startswith(prefixo + "/"):
                    for recurso in recursos:
                        assert rota.name in OPERACOES_RECURSOS[recurso], (rota.path, recurso)


def preparar_convenio(client, headers):
    paciente = criar(client, headers, "/pacientes", {
        "nome": "Paciente ficticio", "documento": "convenio-1", "nascimento": "1990-01-01",
    })
    convenio = criar(client, headers, "/convenios", {"nome": "Operadora ficticia"})
    plano = criar(client, headers, "/planos", {"convenio_id": convenio["id"], "nome": "Plano ficticio"})
    procedimento = criar(client, headers, "/procedimentos", {"codigo": "P-1", "descricao": "Procedimento ficticio"})
    cobertura = criar(client, headers, "/coberturas", {"plano_id": plano["id"], "procedimento_id": procedimento["id"]})
    carteirinha = criar(client, headers, "/carteirinhas", {
        "paciente_id": paciente["id"], "plano_id": plano["id"], "numero": "FICTICIO-1",
        "inicio": "2000-01-01", "fim": "2099-12-31",
    })
    return paciente, convenio, plano, procedimento, cobertura, carteirinha


def test_autorizacao_convenio_regras_e_idempotencia(client):
    headers = autenticar(client)
    paciente, convenio, plano, procedimento, cobertura, carteirinha = preparar_convenio(client, headers)
    dados = {"carteirinha_id": carteirinha["id"], "procedimento_id": procedimento["id"], "idempotencia": str(uuid4())}
    aprovada = criar(client, headers, "/autorizacoes-convenio", dados)
    assert (aprovada["paciente_id"], aprovada["status"], aprovada["motivo"]) == (paciente["id"], "aprovada", "aprovada")
    resposta = client.post("/autorizacoes-convenio", headers=headers, json=dados)
    assert resposta.status_code == 200 and resposta.json() == aprovada
    outro_procedimento = criar(client, headers, "/procedimentos", {"codigo": "P-2", "descricao": "Outro"})
    assert client.post("/autorizacoes-convenio", headers=headers, json={
        **dados, "procedimento_id": outro_procedimento["id"],
    }).status_code == 409

    def nova(**campos):
        return criar(client, headers, "/autorizacoes-convenio", {**dados, "idempotencia": str(uuid4()), **campos})

    negada = nova(procedimento_id=outro_procedimento["id"])
    assert (negada["status"], negada["motivo"]) == ("negada", "sem_cobertura")
    cobranca = criar(client, headers, "/cobrancas", {
        "paciente_id": paciente["id"], "convenio_id": convenio["id"], "descricao": "Teste", "valor": "10.00",
    })
    assert client.post("/guias-convenio", headers=headers, json={
        "autorizacao_id": negada["id"], "cobranca_id": cobranca["id"],
    }).status_code == 409
    assert client.put(f"/coberturas/{cobertura['id']}", headers=headers, json={"ativa": False}).status_code == 200
    assert nova()["motivo"] == "sem_cobertura"
    assert client.put(f"/coberturas/{cobertura['id']}", headers=headers, json={"ativa": True}).status_code == 200
    vigencia = {"inicio": "2000-01-01", "fim": "2000-12-31", "ativa": True}
    assert client.put(f"/carteirinhas/{carteirinha['id']}", headers=headers, json=vigencia).status_code == 200
    assert nova()["motivo"] == "fora_vigencia"
    assert client.put(f"/carteirinhas/{carteirinha['id']}", headers=headers, json={**vigencia, "ativa": False}).status_code == 200
    assert nova()["motivo"] == "carteirinha_inativa"
    assert client.put(f"/planos/{plano['id']}/status", headers=headers, json={"ativo": False}).status_code == 200
    assert nova()["motivo"] == "plano_inativo"
    assert client.put(f"/carteirinhas/{carteirinha['id']}", headers=headers, json={
        "inicio": "2099-01-01", "fim": "2000-01-01",
    }).status_code == 422
    assert client.get(f"/autorizacoes-convenio/{aprovada['id']}", headers=headers).json()["status"] == "aprovada"


def test_guia_convenio_reenvio_auditoria_e_cobranca(client):
    headers = autenticar(client)
    paciente, convenio, plano, procedimento, cobertura, carteirinha = preparar_convenio(client, headers)
    autorizacao = criar(client, headers, "/autorizacoes-convenio", {
        "carteirinha_id": carteirinha["id"], "procedimento_id": procedimento["id"], "idempotencia": str(uuid4()),
    })
    cobranca = criar(client, headers, "/cobrancas", {
        "paciente_id": paciente["id"], "convenio_id": convenio["id"], "descricao": "Teste", "valor": "100.00",
    })
    outro = criar(client, headers, "/pacientes", {"nome": "Outro", "documento": "convenio-2", "nascimento": "1990-01-01"})
    cobranca_errada = criar(client, headers, "/cobrancas", {
        "paciente_id": outro["id"], "convenio_id": convenio["id"], "descricao": "Teste", "valor": "10.00",
    })
    assert client.post("/guias-convenio", headers=headers, json={
        "autorizacao_id": autorizacao["id"], "cobranca_id": cobranca_errada["id"],
    }).status_code == 409
    outro_convenio = criar(client, headers, "/convenios", {"nome": "Outro convenio"})
    cobranca_errada = criar(client, headers, "/cobrancas", {
        "paciente_id": paciente["id"], "convenio_id": outro_convenio["id"], "descricao": "Teste", "valor": "10.00",
    })
    assert client.post("/guias-convenio", headers=headers, json={
        "autorizacao_id": autorizacao["id"], "cobranca_id": cobranca_errada["id"],
    }).status_code == 409
    guia_dados = {"autorizacao_id": autorizacao["id"], "cobranca_id": cobranca["id"]}
    guia = criar(client, headers, "/guias-convenio", guia_dados)
    assert guia["status"] == "rascunho"
    assert client.post("/guias-convenio", headers=headers, json=guia_dados).status_code == 409
    assert client.put(f"/coberturas/{cobertura['id']}", headers=headers, json={"ativa": False}).status_code == 200
    envio = {"idempotencia": str(uuid4())}
    caminho = f"/guias-convenio/{guia['id']}/enviar"
    rejeitada = criar(client, headers, caminho, envio)
    assert (rejeitada["status"], rejeitada["motivo"]) == ("rejeitada", "sem_cobertura")
    assert client.put(f"/coberturas/{cobertura['id']}", headers=headers, json={"ativa": True}).status_code == 200
    repetida = client.post(caminho, headers=headers, json=envio)
    assert repetida.status_code == 200 and repetida.json() == rejeitada
    aceita = criar(client, headers, caminho, {"idempotencia": str(uuid4())})
    assert aceita["status"] == "aceita"
    assert client.post(caminho, headers=headers, json={"idempotencia": str(uuid4())}).status_code == 409
    assert len(client.get(f"/guias-convenio/{guia['id']}/tentativas", headers=headers).json()) == 2
    assert client.get(f"/cobrancas/{cobranca['id']}", headers=headers).json()["valor_pago"] == cobranca["valor_pago"]
    auditoria = client.get("/auditoria", headers=headers, params={"recurso": "carteirinhas"}).json()
    assert auditoria and "FICTICIO-1" not in str(auditoria)


def test_convenios_permissoes_e_concorrencia(client):
    admin = autenticar(client)
    paciente, convenio, plano, procedimento, cobertura, carteirinha = preparar_convenio(client, admin)
    usuario = criar(client, admin, "/usuarios", {
        "nome": "Recepcao", "login": "recepcao-convenio", "senha": "senha-segura", "perfil": "recepcao",
    })
    recepcao = autenticar(client, "recepcao-convenio")
    assert client.post("/planos", headers=recepcao, json={"convenio_id": convenio["id"], "nome": "Outro"}).status_code == 403
    for recurso in ("pacientes", "convenios"):
        caminho = f"/usuarios/{usuario['id']}/recursos/{recurso}"
        assert client.put(caminho, headers=admin, json={"permitida": False}).status_code == 200
        assert client.get("/carteirinhas", headers=recepcao).status_code == 403
        assert client.put(caminho, headers=admin, json={"permitida": True}).status_code == 200
    dados = {"carteirinha_id": carteirinha["id"], "procedimento_id": procedimento["id"], "idempotencia": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda _: client.post("/autorizacoes-convenio", headers=recepcao, json=dados), range(2)))
    assert sorted(r.status_code for r in respostas) == [200, 201]
    assert respostas[0].json()["id"] == respostas[1].json()["id"]
    assert client.post("/autorizacoes-convenio", headers=admin, json=dados).status_code == 409
    cobranca = criar(client, admin, "/cobrancas", {
        "paciente_id": paciente["id"], "convenio_id": convenio["id"], "descricao": "Teste", "valor": "10.00",
    })
    guia = criar(client, recepcao, "/guias-convenio", {
        "autorizacao_id": respostas[0].json()["id"], "cobranca_id": cobranca["id"],
    })
    envio = {"idempotencia": str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as executor:
        respostas = list(executor.map(lambda _: client.post(
            f"/guias-convenio/{guia['id']}/enviar", headers=recepcao, json=envio
        ), range(2)))
    assert sorted(r.status_code for r in respostas) == [200, 201]
    assert respostas[0].json()["id"] == respostas[1].json()["id"]
