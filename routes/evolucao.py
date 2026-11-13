from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from dependencies.autenticacao import exigir_perfis, verificar_operacoes
from models import (
    AdministracaoMedicamento, Alergia, Auditoria, Cobranca, Consulta, Convenio, Diagnostico,
    Disponibilidade, EventoSeguranca, EvolucaoClinica, Exame, Internacao,
    LoteMedicamento, Medicamento, MovimentacaoEstoque, Paciente, Pagamento, Prescricao,
    Profissional, Prontuario, User, VinculoPaciente,
)
from schemas import evolucao as s
from schemas import hospital as h
from schemas import clinico as c
from services.estoque import preparar_movimentacao
from services.hospital import auditar, buscar, pacientes_permitidos, registrar_leitura, salvar, utc, verificar_autoria, verificar_paciente

router = APIRouter()
admin = exigir_perfis("admin")
financeiro = exigir_perfis("admin", "recepcao")
estoque_leitura = exigir_perfis("admin", "medico", "enfermagem")
estoque_escrita = exigir_perfis("admin", "enfermagem")
clinico = exigir_perfis("admin", "medico", "enfermagem")


@router.put("/usuarios/{identificador}/profissional", response_model=h.UsuarioSaida, tags=["usuarios"])
def vincular_usuario(
    identificador: int,
    dados: s.VincularProfissional,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    alvo = buscar(db, User, identificador)
    if alvo.perfil not in ("medico", "enfermagem"):
        raise HTTPException(status_code=422, detail="Apenas usuarios clinicos podem ser vinculados")
    buscar(db, Profissional, dados.profissional_id)
    alvo.profissional_id = dados.profissional_id
    return salvar(db, alvo, usuario, "alterar")


@router.post("/vinculos", response_model=s.VinculoSaida, status_code=201, tags=["vinculos"])
def criar_vinculo(
    dados: s.VinculoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    buscar(db, Paciente, dados.paciente_id)
    buscar(db, Profissional, dados.profissional_id)
    return salvar(db, VinculoPaciente(**dados.model_dump()), usuario)


@router.get("/vinculos", response_model=list[s.VinculoSaida], tags=["vinculos"])
def listar_vinculos(
    profissional_id: int | None = Query(None, gt=0),
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    consulta = select(VinculoPaciente)
    if profissional_id is not None:
        consulta = consulta.where(VinculoPaciente.profissional_id == profissional_id)
    if paciente_id is not None:
        consulta = consulta.where(VinculoPaciente.paciente_id == paciente_id)
    return db.scalars(consulta.order_by(VinculoPaciente.id).offset(offset).limit(limit)).all()


@router.delete("/vinculos/{identificador}", status_code=204, tags=["vinculos"])
def remover_vinculo(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    vinculo = buscar(db, VinculoPaciente, identificador)
    auditar(db, usuario, "remover", vinculo)
    db.delete(vinculo)
    db.commit()


@router.post("/disponibilidades", response_model=s.DisponibilidadeSaida, status_code=201, tags=["agenda"])
def criar_disponibilidade(
    dados: s.DisponibilidadeCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    buscar(db, Profissional, dados.profissional_id)
    return salvar(db, Disponibilidade(**dados.model_dump()), usuario)


@router.get("/disponibilidades", response_model=list[s.DisponibilidadeSaida], tags=["agenda"])
def listar_disponibilidades(
    profissional_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(exigir_perfis("admin", "medico", "enfermagem", "recepcao")),
):
    consulta = select(Disponibilidade)
    if profissional_id is not None:
        consulta = consulta.where(Disponibilidade.profissional_id == profissional_id)
    return db.scalars(consulta.order_by(Disponibilidade.inicio, Disponibilidade.id).offset(offset).limit(limit)).all()


@router.delete("/disponibilidades/{identificador}", status_code=204, tags=["agenda"])
def remover_disponibilidade(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    janela = buscar(db, Disponibilidade, identificador)
    db.execute(update(Profissional).where(Profissional.id == janela.profissional_id).values(
        versao_agenda=Profissional.versao_agenda + 1
    ))
    consultas = db.scalars(select(Consulta).where(
        Consulta.profissional_id == janela.profissional_id,
        Consulta.status == "agendada",
    )).all()
    if any(utc(c.data_hora) < utc(janela.fim) and utc(janela.inicio) < utc(c.data_hora) + timedelta(minutes=c.duracao_minutos) for c in consultas):
        raise HTTPException(status_code=409, detail="Disponibilidade possui consultas agendadas")
    auditar(db, usuario, "remover", janela)
    db.delete(janela)
    db.commit()


@router.get("/auditoria", response_model=list[s.AuditoriaSaida], tags=["auditoria"])
def listar_auditoria(
    recurso: str | None = Query(None, min_length=1, max_length=40),
    registro_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    consulta = select(Auditoria)
    if recurso is not None:
        consulta = consulta.where(Auditoria.recurso == recurso)
    if registro_id is not None:
        consulta = consulta.where(Auditoria.registro_id == registro_id)
    return db.scalars(consulta.order_by(Auditoria.id).offset(offset).limit(limit)).all()


@router.get("/pacientes/{identificador}/historico", tags=["pacientes"])
def historico(
    identificador: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(clinico),
):
    buscar(db, Paciente, identificador)
    verificar_paciente(db, usuario, identificador)
    verificar_operacoes(db, usuario, (
        "listar_consultas", "listar_internacoes", "listar_prontuarios",
        "listar_prescricoes", "listar_exames", "listar_alergias",
        "listar_diagnosticos", "listar_evolucoes", "listar_administracoes",
    ))
    tipos = (
        ("consultas", Consulta, h.ConsultaSaida),
        ("internacoes", Internacao, h.InternacaoSaida),
        ("prontuarios", Prontuario, h.ProntuarioSaida),
        ("prescricoes", Prescricao, h.PrescricaoSaida),
        ("exames", Exame, h.ExameSaida),
        ("alergias", Alergia, c.AlergiaSaida),
        ("diagnosticos", Diagnostico, c.DiagnosticoSaida),
        ("evolucoes", EvolucaoClinica, c.EvolucaoSaida),
        ("administracoes", AdministracaoMedicamento, c.AdministracaoSaida),
    )
    resultado = {}
    registros = []
    for nome, modelo, schema in tipos:
        itens = db.scalars(select(modelo).where(
            modelo.paciente_id == identificador
        ).order_by(modelo.id).offset(offset).limit(limit)).all()
        registros.extend(itens)
        resultado[nome] = [schema.model_validate(item).model_dump(mode="json") for item in itens]
    registrar_leitura(db, usuario, registros)
    return resultado


def administracao_existente(db: Session, dados: c.AdministracaoCriar, usuario_id: int):
    existente = db.scalar(select(AdministracaoMedicamento).where(
        AdministracaoMedicamento.idempotencia == str(dados.idempotencia)
    ))
    if existente is None:
        return None
    corresponde = (
        existente.usuario_id == usuario_id
        and existente.prescricao_id == dados.prescricao_id
        and existente.profissional_id == dados.profissional_id
        and existente.lote_id == dados.lote_id
        and utc(existente.data_hora) == dados.data_hora
        and existente.quantidade == dados.quantidade
        and existente.dose == dados.dose
        and existente.via == dados.via
    )
    if not corresponde:
        raise HTTPException(status_code=409, detail="Chave de idempotencia ja utilizada")
    return existente


@router.post("/administracoes", response_model=c.AdministracaoSaida, status_code=201, tags=["administracoes"])
def criar_administracao(
    dados: c.AdministracaoCriar,
    response: Response,
    db: Session = Depends(get_db),
    usuario: User = Depends(clinico),
):
    prescricao = buscar(db, Prescricao, dados.prescricao_id)
    verificar_paciente(db, usuario, prescricao.paciente_id)
    verificar_autoria(usuario, dados.profissional_id)
    buscar(db, Profissional, dados.profissional_id)
    if prescricao.medicamento_id is None:
        raise HTTPException(status_code=409, detail="Prescricao sem medicamento cadastrado")
    usuario_id = usuario.id
    existente = administracao_existente(db, dados, usuario_id)
    if existente is not None:
        registrar_leitura(db, usuario, [existente])
        response.status_code = 200
        return existente
    valores = dados.model_dump(exclude={"idempotencia"})
    administracao = AdministracaoMedicamento(
        **valores, idempotencia=str(dados.idempotencia),
        paciente_id=prescricao.paciente_id, usuario_id=usuario_id,
    )
    db.add(administracao)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        existente = administracao_existente(db, dados, usuario_id)
        if existente is None:
            raise HTTPException(status_code=409, detail="Conflito de dados ou referencia inexistente") from exc
        registrar_leitura(db, usuario, [existente])
        response.status_code = 200
        return existente
    movimentacao = preparar_movimentacao(
        db, usuario, prescricao.medicamento_id, dados.lote_id, "saida", dados.quantidade,
    )
    db.add(movimentacao)
    db.flush()
    administracao.movimentacao_id = movimentacao.id
    return salvar(db, administracao, usuario)


@router.get("/administracoes", response_model=list[c.AdministracaoSaida], tags=["administracoes"])
def listar_administracoes(
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(clinico),
):
    consulta = select(AdministracaoMedicamento)
    if usuario.perfil != "admin":
        consulta = consulta.where(AdministracaoMedicamento.paciente_id.in_(pacientes_permitidos(usuario)))
    if paciente_id is not None:
        consulta = consulta.where(AdministracaoMedicamento.paciente_id == paciente_id)
    registros = db.scalars(consulta.order_by(AdministracaoMedicamento.id).offset(offset).limit(limit)).all()
    registrar_leitura(db, usuario, registros)
    return registros


@router.get("/administracoes/{identificador}", response_model=c.AdministracaoSaida, tags=["administracoes"])
def obter_administracao(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(clinico),
):
    administracao = buscar(db, AdministracaoMedicamento, identificador)
    verificar_paciente(db, usuario, administracao.paciente_id)
    registrar_leitura(db, usuario, [administracao])
    return administracao


@router.post("/medicamentos", response_model=s.MedicamentoSaida, status_code=201, tags=["estoque"])
def criar_medicamento(
    dados: s.MedicamentoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    return salvar(db, Medicamento(**dados.model_dump()), usuario)


@router.get("/medicamentos", response_model=list[s.MedicamentoSaida], tags=["estoque"])
def listar_medicamentos(
    q: str | None = Query(None, min_length=1, max_length=120),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_leitura),
):
    consulta = select(Medicamento)
    if q is not None:
        consulta = consulta.where(Medicamento.nome.ilike(f"%{q}%"))
    return db.scalars(consulta.order_by(Medicamento.id).offset(offset).limit(limit)).all()


@router.get("/medicamentos/{identificador}", response_model=s.MedicamentoSaida, tags=["estoque"])
def obter_medicamento(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_leitura),
):
    return buscar(db, Medicamento, identificador)


@router.put("/medicamentos/{identificador}/estoque-minimo", response_model=s.MedicamentoSaida, tags=["estoque"])
def alterar_estoque_minimo(
    identificador: int,
    dados: s.EstoqueMinimo,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    medicamento = buscar(db, Medicamento, identificador)
    medicamento.estoque_minimo = dados.estoque_minimo
    return salvar(db, medicamento, usuario, "alterar")


@router.post("/estoque/lotes", response_model=s.LoteSaida, status_code=201, tags=["estoque"])
def criar_lote(
    dados: s.LoteCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_escrita),
):
    buscar(db, Medicamento, dados.medicamento_id)
    return salvar(db, LoteMedicamento(**dados.model_dump()), usuario)


@router.get("/estoque/lotes", response_model=list[s.LoteSaida], tags=["estoque"])
def listar_lotes(
    medicamento_id: int | None = Query(None, gt=0),
    vencido: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_leitura),
):
    consulta = select(LoteMedicamento)
    if medicamento_id is not None:
        consulta = consulta.where(LoteMedicamento.medicamento_id == medicamento_id)
    if vencido is not None:
        hoje = datetime.now(timezone.utc).date()
        consulta = consulta.where(LoteMedicamento.validade < hoje if vencido else LoteMedicamento.validade >= hoje)
    return db.scalars(consulta.order_by(LoteMedicamento.validade, LoteMedicamento.id).offset(offset).limit(limit)).all()


def quantidade_disponivel():
    return select(func.coalesce(func.sum(LoteMedicamento.quantidade), 0)).where(
        LoteMedicamento.medicamento_id == Medicamento.id,
        LoteMedicamento.validade >= datetime.now(timezone.utc).date(),
    ).correlate(Medicamento).scalar_subquery()


@router.get("/estoque/alertas", response_model=list[s.EstoqueAlerta], tags=["estoque"])
def alertas_estoque(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_leitura),
):
    disponivel = quantidade_disponivel()
    resultados = db.execute(select(Medicamento.id, Medicamento.nome, Medicamento.estoque_minimo, disponivel.label("quantidade_disponivel")).where(
        disponivel <= Medicamento.estoque_minimo
    ).order_by(Medicamento.id).offset(offset).limit(limit)).all()
    return [
        s.EstoqueAlerta(medicamento_id=item.id, nome=item.nome, estoque_minimo=item.estoque_minimo, quantidade_disponivel=item.quantidade_disponivel)
        for item in resultados
    ]


@router.get("/monitoramento", tags=["monitoramento"])
def monitoramento(
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    negacoes = db.scalar(select(func.count()).select_from(EventoSeguranca).where(
        EventoSeguranca.evento == "acesso_negado", EventoSeguranca.data_hora >= limite,
    ))
    bloqueios = db.scalar(select(func.count()).select_from(EventoSeguranca).where(
        EventoSeguranca.evento == "limite_login", EventoSeguranca.data_hora >= limite,
    ))
    alertas = db.scalar(select(func.count()).select_from(Medicamento).where(
        quantidade_disponivel() <= Medicamento.estoque_minimo
    ))
    return {"acessos_negados_24h": negacoes, "limites_login_24h": bloqueios, "medicamentos_com_estoque_baixo": alertas}


@router.post("/estoque/movimentacoes", response_model=s.MovimentacaoSaida, status_code=201, tags=["estoque"])
def movimentar_estoque(
    dados: s.MovimentacaoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_escrita),
):
    movimentacao = preparar_movimentacao(
        db, usuario, dados.medicamento_id, dados.lote_id, dados.tipo, dados.quantidade,
    )
    return salvar(db, movimentacao)


@router.post("/estoque/regularizacoes", response_model=s.MovimentacaoSaida, status_code=201, tags=["estoque"])
def regularizar_estoque(
    dados: s.RegularizacaoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_escrita),
):
    lote = buscar(db, LoteMedicamento, dados.lote_id)
    resultado = db.execute(update(Medicamento).where(
        Medicamento.id == lote.medicamento_id,
        Medicamento.quantidade_nao_rastreada >= dados.quantidade,
    ).values(quantidade_nao_rastreada=Medicamento.quantidade_nao_rastreada - dados.quantidade))
    if resultado.rowcount != 1:
        raise HTTPException(status_code=409, detail="Saldo nao rastreado insuficiente")
    resultado_lote = db.execute(update(LoteMedicamento).where(
        LoteMedicamento.id == lote.id,
        LoteMedicamento.quantidade <= 2147483647 - dados.quantidade,
    ).values(quantidade=LoteMedicamento.quantidade + dados.quantidade))
    if resultado_lote.rowcount != 1:
        raise HTTPException(status_code=409, detail="Quantidade do lote invalida")
    return salvar(db, MovimentacaoEstoque(
        medicamento_id=lote.medicamento_id, lote_id=lote.id, tipo="regularizacao",
        quantidade=dados.quantidade, usuario_id=usuario.id, data_hora=datetime.now(timezone.utc),
    ))


@router.get("/estoque/movimentacoes", response_model=list[s.MovimentacaoSaida], tags=["estoque"])
def listar_movimentacoes(
    medicamento_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(estoque_leitura),
):
    consulta = select(MovimentacaoEstoque)
    if medicamento_id is not None:
        consulta = consulta.where(MovimentacaoEstoque.medicamento_id == medicamento_id)
    return db.scalars(consulta.order_by(MovimentacaoEstoque.id).offset(offset).limit(limit)).all()


@router.post("/convenios", response_model=s.ConvenioSaida, status_code=201, tags=["faturamento"])
def criar_convenio(
    dados: s.ConvenioCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(admin),
):
    return salvar(db, Convenio(**dados.model_dump()))


@router.get("/convenios", response_model=list[s.ConvenioSaida], tags=["faturamento"])
def listar_convenios(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    return db.scalars(select(Convenio).order_by(Convenio.id).offset(offset).limit(limit)).all()


@router.get("/convenios/{identificador}", response_model=s.ConvenioSaida, tags=["faturamento"])
def obter_convenio(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    return buscar(db, Convenio, identificador)


@router.post("/cobrancas", response_model=s.CobrancaSaida, status_code=201, tags=["faturamento"])
def criar_cobranca(
    dados: s.CobrancaCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    buscar(db, Paciente, dados.paciente_id)
    if dados.convenio_id is not None:
        buscar(db, Convenio, dados.convenio_id)
    return salvar(db, Cobranca(
        paciente_id=dados.paciente_id, convenio_id=dados.convenio_id,
        descricao=dados.descricao, valor_centavos=int(dados.valor * 100),
    ))


@router.get("/cobrancas", response_model=list[s.CobrancaSaida], tags=["faturamento"])
def listar_cobrancas(
    paciente_id: int | None = Query(None, gt=0),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    consulta = select(Cobranca)
    if paciente_id is not None:
        consulta = consulta.where(Cobranca.paciente_id == paciente_id)
    return db.scalars(consulta.order_by(Cobranca.id).offset(offset).limit(limit)).all()


@router.get("/cobrancas/{identificador}", response_model=s.CobrancaSaida, tags=["faturamento"])
def obter_cobranca(
    identificador: int,
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    return buscar(db, Cobranca, identificador)


@router.post("/cobrancas/{identificador}/pagamentos", response_model=s.PagamentoSaida, status_code=201, tags=["faturamento"])
def pagar_cobranca(
    identificador: int,
    dados: s.PagamentoCriar,
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    buscar(db, Cobranca, identificador)
    centavos = int(dados.valor * 100)
    resultado = db.execute(update(Cobranca).where(
        Cobranca.id == identificador,
        Cobranca.pago_centavos + centavos <= Cobranca.valor_centavos,
    ).values(pago_centavos=Cobranca.pago_centavos + centavos))
    if resultado.rowcount != 1:
        raise HTTPException(status_code=409, detail="Pagamento excede saldo da cobranca")
    return salvar(db, Pagamento(
        cobranca_id=identificador, usuario_id=usuario.id,
        valor_centavos=centavos, data_hora=datetime.now(timezone.utc),
    ))


@router.get("/cobrancas/{identificador}/pagamentos", response_model=list[s.PagamentoSaida], tags=["faturamento"])
def listar_pagamentos(
    identificador: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    usuario: User = Depends(financeiro),
):
    buscar(db, Cobranca, identificador)
    return db.scalars(select(Pagamento).where(
        Pagamento.cobranca_id == identificador
    ).order_by(Pagamento.id).offset(offset).limit(limit)).all()
