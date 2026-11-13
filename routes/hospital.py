from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import AwareDatetime
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from core.jwt import criar_token_acesso
from core.senha_hash import criar_hash_senha, verificar_senha
from database import get_db
from dependencies.autenticacao import exigir_perfis, get_usuario_atual
from models import Alergia, Consulta, Diagnostico, EventoSeguranca, EvolucaoClinica, Exame, Internacao, Leito, Medicamento, Paciente, Prescricao, Profissional, Prontuario, User
from schemas import clinico as c
from schemas import hospital as s
from services.hospital import (
    buscar, pacientes_permitidos, registrar_leitura, salvar, validar_agendamento,
    verificar_autoria, verificar_paciente, vincular_paciente,
)
from services.limite_login import identificador_ip, registrar_falha, registrar_sucesso, verificar_limite

router = APIRouter()


@router.post("/auth/login", tags=["autenticacao"])
def login(dados: s.Login, request: Request, db: Session = Depends(get_db)):
    identificador = identificador_ip(request)
    verificar_limite(db, identificador)
    usuario = db.scalar(select(User).where(User.login == dados.login))
    if not usuario or not usuario.ativo or not verificar_senha(dados.senha, usuario.senha_hash):
        registrar_falha(db, identificador)
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    registrar_sucesso(db, identificador)
    return {"access_token": criar_token_acesso(usuario.id, usuario.versao_token), "token_type": "bearer"}


@router.get("/auth/me", response_model=s.UsuarioSaida, tags=["autenticacao"])
def usuario_atual(usuario: User = Depends(get_usuario_atual)):
    return usuario


@router.post("/auth/logout", status_code=204, tags=["autenticacao"])
def logout(usuario: User = Depends(get_usuario_atual), db: Session = Depends(get_db)):
    db.execute(update(User).where(User.id == usuario.id).values(versao_token=User.versao_token + 1))
    db.add(EventoSeguranca(usuario_id=usuario.id, evento="sessoes_revogadas", operacao="logout", data_hora=datetime.now(timezone.utc)))
    db.commit()


@router.post("/usuarios", response_model=s.UsuarioSaida, status_code=201, tags=["usuarios"])
def criar_usuario(
    dados: s.UsuarioCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis("admin")),
):
    return salvar(db, User(nome=dados.nome, login=dados.login, senha_hash=criar_hash_senha(dados.senha), perfil=dados.perfil.value))


@router.get("/usuarios", response_model=list[s.UsuarioSaida], tags=["usuarios"])
def listar_usuarios(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis("admin")),
):
    return db.scalars(select(User).order_by(User.id).offset(offset).limit(limit)).all()


def registrar_recurso(caminho, modelo, entrada, saida, leitura, escrita, criar_habilitado=True):
    def criar(
        dados: entrada,
        db: Session = Depends(get_db),
        usuario: User = Depends(exigir_perfis(*escrita)),
    ):
        valores = dados.model_dump()
        if "paciente_id" in valores:
            buscar(db, Paciente, valores["paciente_id"])
        if "profissional_id" in valores:
            buscar(db, Profissional, valores["profissional_id"])
        if modelo in (Prontuario, Prescricao, Exame, Alergia, Diagnostico, EvolucaoClinica):
            verificar_paciente(db, usuario, valores["paciente_id"])
            verificar_autoria(usuario, valores["profissional_id"])
        if modelo is Prescricao and valores["medicamento_id"] is not None:
            medicamento = buscar(db, Medicamento, valores["medicamento_id"])
            if medicamento.nome.casefold() != valores["medicamento"].casefold():
                raise HTTPException(status_code=422, detail="Medicamento nao corresponde ao cadastro")
        return salvar(db, modelo(**valores), usuario if modelo in sensiveis else None)

    def listar(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        paciente_id: int | None = Query(None, gt=0),
        q: str | None = Query(None, min_length=1, max_length=120),
        disponivel: bool | None = None,
        desde: AwareDatetime | None = None,
        ate: AwareDatetime | None = None,
        db: Session = Depends(get_db),
        usuario: User = Depends(exigir_perfis(*leitura)),
    ):
        consulta = select(modelo)
        campo_paciente = modelo.id if modelo is Paciente else getattr(modelo, "paciente_id", None)
        if campo_paciente is not None and usuario.perfil in ("medico", "enfermagem"):
            consulta = consulta.where(campo_paciente.in_(pacientes_permitidos(usuario)))
        if paciente_id is not None:
            if campo_paciente is None:
                raise HTTPException(status_code=422, detail="Filtro paciente_id nao aplicavel")
            consulta = consulta.where(campo_paciente == paciente_id)
        if q is not None:
            if modelo not in (Paciente, Profissional):
                raise HTTPException(status_code=422, detail="Filtro q nao aplicavel")
            identificador = Paciente.documento if modelo is Paciente else Profissional.registro
            consulta = consulta.where(or_(modelo.nome.ilike(f"%{q}%"), identificador.ilike(f"%{q}%")))
        if disponivel is not None:
            if modelo is not Leito:
                raise HTTPException(status_code=422, detail="Filtro disponivel nao aplicavel")
            ocupados = select(Internacao.leito_ativo_id).where(Internacao.leito_ativo_id.is_not(None))
            consulta = consulta.where(~Leito.id.in_(ocupados) if disponivel else Leito.id.in_(ocupados))
        if desde is not None or ate is not None:
            if modelo is not Consulta:
                raise HTTPException(status_code=422, detail="Filtro de data nao aplicavel")
            if desde is not None and ate is not None and desde > ate:
                raise HTTPException(status_code=422, detail="Periodo de consulta invalido")
            if desde is not None:
                consulta = consulta.where(Consulta.data_hora >= desde.astimezone(timezone.utc))
            if ate is not None:
                consulta = consulta.where(Consulta.data_hora <= ate.astimezone(timezone.utc))
        objetos = db.scalars(consulta.order_by(modelo.id).offset(offset).limit(limit)).all()
        if modelo in sensiveis:
            registrar_leitura(db, usuario, objetos)
        return objetos

    def obter(
        identificador: int,
        db: Session = Depends(get_db),
        usuario: User = Depends(exigir_perfis(*leitura)),
    ):
        objeto = buscar(db, modelo, identificador)
        paciente_id = objeto.id if modelo is Paciente else getattr(objeto, "paciente_id", None)
        if paciente_id is not None:
            verificar_paciente(db, usuario, paciente_id)
        if modelo in sensiveis:
            registrar_leitura(db, usuario, [objeto])
        return objeto

    if criar_habilitado:
        router.add_api_route(caminho, criar, methods=["POST"], response_model=saida, status_code=201, tags=[caminho[1:]], name=f"criar_{caminho[1:]}")
    router.add_api_route(caminho, listar, methods=["GET"], response_model=list[saida], tags=[caminho[1:]], name=f"listar_{caminho[1:]}")
    router.add_api_route(f"{caminho}/{{identificador}}", obter, methods=["GET"], response_model=saida, tags=[caminho[1:]], name=f"obter_{caminho[1:]}")


todos = ("admin", "medico", "enfermagem", "recepcao")
clinicos = ("admin", "medico", "enfermagem")
medicos = ("admin", "medico")
sensiveis = (Paciente, Consulta, Prontuario, Prescricao, Exame, Alergia, Diagnostico, EvolucaoClinica)

registrar_recurso("/pacientes", Paciente, s.PacienteCriar, s.PacienteSaida, todos, ("admin", "recepcao"))
registrar_recurso("/profissionais", Profissional, s.ProfissionalCriar, s.ProfissionalSaida, todos, ("admin",))
registrar_recurso("/consultas", Consulta, s.ConsultaCriar, s.ConsultaSaida, todos, ("admin", "recepcao"), criar_habilitado=False)
registrar_recurso("/prontuarios", Prontuario, s.ProntuarioCriar, s.ProntuarioSaida, clinicos, medicos)
registrar_recurso("/leitos", Leito, s.LeitoCriar, s.LeitoSaida, todos, ("admin",))
registrar_recurso("/prescricoes", Prescricao, s.PrescricaoCriar, s.PrescricaoSaida, clinicos, medicos)
registrar_recurso("/exames", Exame, s.ExameCriar, s.ExameSaida, clinicos, medicos)
registrar_recurso("/alergias", Alergia, c.AlergiaCriar, c.AlergiaSaida, clinicos, clinicos)
registrar_recurso("/diagnosticos", Diagnostico, c.DiagnosticoCriar, c.DiagnosticoSaida, clinicos, medicos)
registrar_recurso("/evolucoes", EvolucaoClinica, c.EvolucaoCriar, c.EvolucaoSaida, clinicos, clinicos)


def registrar_atualizacao(caminho, modelo, entrada, saida, perfis):
    def atualizar(
        identificador: int,
        dados: entrada,
        db: Session = Depends(get_db),
        usuario: User = Depends(exigir_perfis(*perfis)),
    ):
        objeto = buscar(db, modelo, identificador)
        for campo, valor in dados.model_dump().items():
            setattr(objeto, campo, valor)
        return salvar(db, objeto, usuario if modelo in sensiveis else None, "alterar")

    router.add_api_route(f"{caminho}/{{identificador}}", atualizar, methods=["PUT"], response_model=saida, tags=[caminho[1:]], name=f"atualizar_{caminho[1:]}")


registrar_atualizacao("/pacientes", Paciente, s.PacienteCriar, s.PacienteSaida, ("admin", "recepcao"))
registrar_atualizacao("/profissionais", Profissional, s.ProfissionalCriar, s.ProfissionalSaida, ("admin",))
registrar_atualizacao("/leitos", Leito, s.LeitoCriar, s.LeitoSaida, ("admin",))


@router.post("/consultas", response_model=s.ConsultaSaida, status_code=201, tags=["consultas"])
def agendar_consulta(
    dados: s.ConsultaCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis("admin", "recepcao")),
):
    buscar(db, Paciente, dados.paciente_id)
    buscar(db, Profissional, dados.profissional_id)
    validar_agendamento(db, dados.profissional_id, dados.data_hora, dados.duracao_minutos)
    vinculo = vincular_paciente(db, dados.profissional_id, dados.paciente_id)
    return salvar(db, Consulta(**dados.model_dump(), horario_ativo=dados.data_hora), usuario, vinculo=vinculo)


@router.post("/consultas/{identificador}/cancelar", response_model=s.ConsultaSaida, tags=["consultas"])
def cancelar_consulta(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis("admin", "recepcao")),
):
    consulta = buscar(db, Consulta, identificador)
    if consulta.status != "agendada":
        raise HTTPException(status_code=409, detail="Consulta nao esta agendada")
    consulta.status = "cancelada"
    consulta.horario_ativo = None
    return salvar(db, consulta, usuario, "alterar")


@router.post("/consultas/{identificador}/concluir", response_model=s.ConsultaSaida, tags=["consultas"])
def concluir_consulta(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*medicos)),
):
    consulta = buscar(db, Consulta, identificador)
    verificar_paciente(db, usuario, consulta.paciente_id)
    verificar_autoria(usuario, consulta.profissional_id)
    if consulta.status != "agendada":
        raise HTTPException(status_code=409, detail="Consulta nao esta agendada")
    consulta.status = "concluida"
    return salvar(db, consulta, usuario, "alterar")


@router.post("/internacoes", response_model=s.InternacaoSaida, status_code=201, tags=["internacoes"])
def internar(
    dados: s.InternacaoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*clinicos)),
):
    buscar(db, Paciente, dados.paciente_id)
    buscar(db, Leito, dados.leito_id)
    buscar(db, Profissional, dados.profissional_id)
    if usuario.perfil != "admin":
        verificar_paciente(db, usuario, dados.paciente_id)
        verificar_autoria(usuario, dados.profissional_id)
    vinculo = vincular_paciente(db, dados.profissional_id, dados.paciente_id)
    return salvar(db, Internacao(
        paciente_id=dados.paciente_id,
        leito_id=dados.leito_id,
        profissional_id=dados.profissional_id,
        paciente_ativo_id=dados.paciente_id,
        leito_ativo_id=dados.leito_id,
        entrada=datetime.now(timezone.utc),
    ), usuario, vinculo=vinculo)


@router.get("/internacoes", response_model=list[s.InternacaoSaida], tags=["internacoes"])
def listar_internacoes(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    paciente_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*clinicos)),
):
    consulta = select(Internacao)
    if usuario.perfil != "admin":
        consulta = consulta.where(Internacao.paciente_id.in_(pacientes_permitidos(usuario)))
    if paciente_id is not None:
        consulta = consulta.where(Internacao.paciente_id == paciente_id)
    objetos = db.scalars(consulta.order_by(Internacao.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, objetos)
    return objetos


@router.get("/internacoes/{identificador}", response_model=s.InternacaoSaida, tags=["internacoes"])
def obter_internacao(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*clinicos)),
):
    internacao = buscar(db, Internacao, identificador)
    verificar_paciente(db, usuario, internacao.paciente_id)
    registrar_leitura(db, usuario, [internacao])
    return internacao


@router.post("/internacoes/{identificador}/alta", response_model=s.InternacaoSaida, tags=["internacoes"])
def dar_alta(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*medicos)),
):
    internacao = buscar(db, Internacao, identificador)
    verificar_paciente(db, usuario, internacao.paciente_id)
    if internacao.alta is not None:
        raise HTTPException(status_code=409, detail="Internacao ja encerrada")
    internacao.alta = datetime.now(timezone.utc)
    internacao.paciente_ativo_id = None
    internacao.leito_ativo_id = None
    return salvar(db, internacao, usuario, "alterar")


@router.put("/exames/{identificador}/resultado", response_model=s.ExameSaida, tags=["exames"])
def registrar_resultado(
    identificador: int,
    dados: s.ResultadoExame,
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis(*medicos)),
):
    exame = buscar(db, Exame, identificador)
    verificar_paciente(db, usuario, exame.paciente_id)
    exame.resultado = dados.resultado
    return salvar(db, exame, usuario, "alterar")
