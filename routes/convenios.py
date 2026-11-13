from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from database import get_db
from dependencies.autenticacao import exigir_perfis
from models import (
    AutorizacaoConvenio, Carteirinha, Cobranca, Cobertura, Convenio, GuiaConvenio,
    Paciente, Plano, Procedimento, TentativaGuia, User,
)
from schemas import convenios as s
from services.hospital import auditar, buscar, registrar_leitura, salvar
from services.operadora_simulada import avaliar, bloquear_plano

router = APIRouter(tags=["convenios e integracao simulada"])
admin = exigir_perfis("admin")
financeiro = exigir_perfis("admin", "recepcao")


@router.post("/planos", response_model=s.PlanoSaida, status_code=201)
def criar_plano(dados: s.PlanoCriar, db: Session = Depends(get_db), usuario: User = Depends(admin)):
    buscar(db, Convenio, dados.convenio_id)
    return salvar(db, Plano(**dados.model_dump()), usuario)


@router.get("/planos", response_model=list[s.PlanoSaida])
def listar_planos(
    convenio_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    consulta = select(Plano)
    if convenio_id is not None:
        consulta = consulta.where(Plano.convenio_id == convenio_id)
    itens = db.scalars(consulta.order_by(Plano.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.put("/planos/{identificador}/status", response_model=s.PlanoSaida)
def alterar_plano(
    identificador: int, dados: s.Ativacao, db: Session = Depends(get_db), usuario: User = Depends(admin),
):
    plano = buscar(db, Plano, identificador)
    bloquear_plano(db, plano.id)
    db.refresh(plano)
    plano.ativo = dados.ativo
    return salvar(db, plano, usuario, "alterar")


@router.post("/procedimentos", response_model=s.ProcedimentoSaida, status_code=201)
def criar_procedimento(
    dados: s.ProcedimentoCriar, db: Session = Depends(get_db), usuario: User = Depends(admin),
):
    return salvar(db, Procedimento(**dados.model_dump()), usuario)


@router.get("/procedimentos", response_model=list[s.ProcedimentoSaida])
def listar_procedimentos(
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    itens = db.scalars(select(Procedimento).order_by(Procedimento.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.post("/coberturas", response_model=s.CoberturaSaida, status_code=201)
def criar_cobertura(
    dados: s.CoberturaCriar, db: Session = Depends(get_db), usuario: User = Depends(admin),
):
    buscar(db, Plano, dados.plano_id)
    buscar(db, Procedimento, dados.procedimento_id)
    bloquear_plano(db, dados.plano_id)
    return salvar(db, Cobertura(**dados.model_dump()), usuario)


@router.get("/coberturas", response_model=list[s.CoberturaSaida])
def listar_coberturas(
    plano_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    consulta = select(Cobertura)
    if plano_id is not None:
        consulta = consulta.where(Cobertura.plano_id == plano_id)
    itens = db.scalars(consulta.order_by(Cobertura.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.put("/coberturas/{identificador}", response_model=s.CoberturaSaida)
def alterar_cobertura(
    identificador: int, dados: s.CoberturaAtualizar,
    db: Session = Depends(get_db), usuario: User = Depends(admin),
):
    cobertura = buscar(db, Cobertura, identificador)
    bloquear_plano(db, cobertura.plano_id)
    db.refresh(cobertura)
    cobertura.ativa = dados.ativa
    return salvar(db, cobertura, usuario, "alterar")


@router.post("/carteirinhas", response_model=s.CarteirinhaSaida, status_code=201)
def criar_carteirinha(
    dados: s.CarteirinhaCriar, db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    buscar(db, Paciente, dados.paciente_id)
    buscar(db, Plano, dados.plano_id)
    bloquear_plano(db, dados.plano_id)
    return salvar(db, Carteirinha(**dados.model_dump()), usuario)


@router.get("/carteirinhas", response_model=list[s.CarteirinhaSaida])
def listar_carteirinhas(
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    consulta = select(Carteirinha)
    if paciente_id is not None:
        consulta = consulta.where(Carteirinha.paciente_id == paciente_id)
    itens = db.scalars(consulta.order_by(Carteirinha.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.get("/carteirinhas/{identificador}", response_model=s.CarteirinhaSaida)
def obter_carteirinha(
    identificador: int, db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    item = buscar(db, Carteirinha, identificador)
    registrar_leitura(db, usuario, [item])
    return item


@router.put("/carteirinhas/{identificador}", response_model=s.CarteirinhaSaida)
def alterar_carteirinha(
    identificador: int, dados: s.Vigencia,
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    item = buscar(db, Carteirinha, identificador)
    bloquear_plano(db, item.plano_id)
    db.refresh(item)
    for campo, valor in dados.model_dump().items():
        setattr(item, campo, valor)
    return salvar(db, item, usuario, "alterar")


@router.post("/autorizacoes-convenio", response_model=s.AutorizacaoSaida, status_code=201)
def solicitar_autorizacao(
    dados: s.AutorizacaoCriar, response: Response,
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    carteirinha = buscar(db, Carteirinha, dados.carteirinha_id)
    buscar(db, Procedimento, dados.procedimento_id)
    bloquear_plano(db, carteirinha.plano_id)
    existente = db.scalar(select(AutorizacaoConvenio).where(
        AutorizacaoConvenio.idempotencia == str(dados.idempotencia)
    ))
    if existente is not None:
        if (existente.usuario_id, existente.carteirinha_id, existente.procedimento_id) != (
            usuario.id, dados.carteirinha_id, dados.procedimento_id
        ):
            raise HTTPException(status_code=409, detail="Chave de idempotencia ja utilizada")
        registrar_leitura(db, usuario, [existente])
        response.status_code = 200
        return existente
    agora = datetime.now(timezone.utc)
    aprovada, motivo = avaliar(db, carteirinha, dados.procedimento_id, agora.date())
    autorizacao = AutorizacaoConvenio(
        carteirinha_id=carteirinha.id, paciente_id=carteirinha.paciente_id,
        procedimento_id=dados.procedimento_id, usuario_id=usuario.id,
        idempotencia=str(dados.idempotencia), data_referencia=agora.date(), data_hora=agora,
        status="aprovada" if aprovada else "negada", motivo=motivo,
    )
    return salvar(db, autorizacao, usuario)


@router.get("/autorizacoes-convenio", response_model=list[s.AutorizacaoSaida])
def listar_autorizacoes_convenio(
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    consulta = select(AutorizacaoConvenio)
    if paciente_id is not None:
        consulta = consulta.where(AutorizacaoConvenio.paciente_id == paciente_id)
    itens = db.scalars(consulta.order_by(AutorizacaoConvenio.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.get("/autorizacoes-convenio/{identificador}", response_model=s.AutorizacaoSaida)
def obter_autorizacao_convenio(
    identificador: int, db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    item = buscar(db, AutorizacaoConvenio, identificador)
    registrar_leitura(db, usuario, [item])
    return item


@router.post("/guias-convenio", response_model=s.GuiaSaida, status_code=201)
def criar_guia_convenio(
    dados: s.GuiaCriar, db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    autorizacao = buscar(db, AutorizacaoConvenio, dados.autorizacao_id)
    cobranca = buscar(db, Cobranca, dados.cobranca_id)
    carteirinha = buscar(db, Carteirinha, autorizacao.carteirinha_id)
    plano = buscar(db, Plano, carteirinha.plano_id)
    if autorizacao.status != "aprovada":
        raise HTTPException(status_code=409, detail="Autorizacao nao aprovada")
    if cobranca.paciente_id != autorizacao.paciente_id or cobranca.convenio_id != plano.convenio_id:
        raise HTTPException(status_code=409, detail="Cobranca nao corresponde ao paciente e convenio")
    guia = GuiaConvenio(
        autorizacao_id=autorizacao.id, cobranca_id=cobranca.id,
        paciente_id=autorizacao.paciente_id, usuario_id=usuario.id,
        data_hora=datetime.now(timezone.utc), status="rascunho",
    )
    return salvar(db, guia, usuario)


@router.get("/guias-convenio", response_model=list[s.GuiaSaida])
def listar_guias_convenio(
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    consulta = select(GuiaConvenio)
    if paciente_id is not None:
        consulta = consulta.where(GuiaConvenio.paciente_id == paciente_id)
    itens = db.scalars(consulta.order_by(GuiaConvenio.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, itens)
    return itens


@router.get("/guias-convenio/{identificador}", response_model=s.GuiaSaida)
def obter_guia_convenio(
    identificador: int, db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    item = buscar(db, GuiaConvenio, identificador)
    registrar_leitura(db, usuario, [item])
    return item


@router.post("/guias-convenio/{identificador}/enviar", response_model=s.TentativaSaida, status_code=201)
def enviar_guia_convenio(
    identificador: int, dados: s.EnvioGuia, response: Response,
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    guia = buscar(db, GuiaConvenio, identificador)
    autorizacao = buscar(db, AutorizacaoConvenio, guia.autorizacao_id)
    carteirinha = buscar(db, Carteirinha, autorizacao.carteirinha_id)
    bloquear_plano(db, carteirinha.plano_id)
    db.execute(update(GuiaConvenio).where(GuiaConvenio.id == identificador).values(
        versao=GuiaConvenio.versao + 1
    ))
    db.refresh(guia)
    existente = db.scalar(select(TentativaGuia).where(TentativaGuia.idempotencia == str(dados.idempotencia)))
    if existente is not None:
        if existente.guia_id != guia.id or existente.usuario_id != usuario.id:
            raise HTTPException(status_code=409, detail="Chave de idempotencia ja utilizada")
        registrar_leitura(db, usuario, [existente])
        response.status_code = 200
        return existente
    if guia.status == "aceita":
        raise HTTPException(status_code=409, detail="Guia ja aceita")
    agora = datetime.now(timezone.utc)
    aceita, motivo = avaliar(db, carteirinha, autorizacao.procedimento_id, agora.date())
    guia.status = "aceita" if aceita else "rejeitada"
    tentativa = TentativaGuia(
        guia_id=guia.id, usuario_id=usuario.id, idempotencia=str(dados.idempotencia),
        data_referencia=agora.date(), data_hora=agora, status=guia.status, motivo=motivo,
    )
    auditar(db, usuario, "alterar", guia)
    return salvar(db, tentativa, usuario, "enviar")


@router.get("/guias-convenio/{identificador}/tentativas", response_model=list[s.TentativaSaida])
def listar_tentativas_guia(
    identificador: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db), usuario: User = Depends(financeiro),
):
    guia = buscar(db, GuiaConvenio, identificador)
    itens = db.scalars(select(TentativaGuia).where(
        TentativaGuia.guia_id == guia.id
    ).order_by(TentativaGuia.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, [guia, *itens])
    return itens
