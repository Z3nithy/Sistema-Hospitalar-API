from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from core.jwt import ler_token_acesso
from database import get_db

from models import RestricaoOperacao, RestricaoRecurso, User
from sqlalchemy import select

security = HTTPBearer()

OPERACOES_RECURSOS = {
    "pacientes": {
        "criar_pacientes", "listar_pacientes", "obter_pacientes", "atualizar_pacientes",
        "agendar_consulta", "listar_consultas", "obter_consultas", "cancelar_consulta", "concluir_consulta",
        "internar", "listar_internacoes", "obter_internacao", "dar_alta", "historico",
        "criar_prontuarios", "listar_prontuarios", "obter_prontuarios",
        "criar_prescricoes", "listar_prescricoes", "obter_prescricoes",
        "criar_exames", "listar_exames", "obter_exames", "registrar_resultado",
        "criar_cobranca", "listar_cobrancas", "obter_cobranca", "pagar_cobranca", "listar_pagamentos",
        "criar_alergias", "listar_alergias", "obter_alergias",
        "criar_diagnosticos", "listar_diagnosticos", "obter_diagnosticos",
        "criar_evolucoes", "listar_evolucoes", "obter_evolucoes",
        "criar_administracao", "listar_administracoes", "obter_administracao",
        "criar_carteirinha", "listar_carteirinhas", "obter_carteirinha", "alterar_carteirinha",
        "solicitar_autorizacao", "listar_autorizacoes_convenio", "obter_autorizacao_convenio",
        "criar_guia_convenio", "listar_guias_convenio", "obter_guia_convenio",
        "enviar_guia_convenio", "listar_tentativas_guia",
    },
    "convenios": {
        "criar_convenio", "listar_convenios", "obter_convenio",
        "criar_plano", "listar_planos", "alterar_plano", "criar_procedimento", "listar_procedimentos",
        "criar_cobertura", "listar_coberturas", "alterar_cobertura",
        "criar_carteirinha", "listar_carteirinhas", "obter_carteirinha", "alterar_carteirinha",
        "solicitar_autorizacao", "listar_autorizacoes_convenio", "obter_autorizacao_convenio",
        "criar_guia_convenio", "listar_guias_convenio", "obter_guia_convenio",
        "enviar_guia_convenio", "listar_tentativas_guia",
    },
    "consultas": {"agendar_consulta", "listar_consultas", "obter_consultas", "cancelar_consulta", "concluir_consulta", "historico"},
    "internacoes": {"internar", "listar_internacoes", "obter_internacao", "dar_alta", "historico"},
    "prontuarios": {"criar_prontuarios", "listar_prontuarios", "obter_prontuarios", "historico"},
    "prescricoes": {"criar_prescricoes", "listar_prescricoes", "obter_prescricoes", "historico", "criar_administracao", "listar_administracoes", "obter_administracao"},
    "exames": {"criar_exames", "listar_exames", "obter_exames", "registrar_resultado", "historico"},
    "alergias": {"criar_alergias", "listar_alergias", "obter_alergias", "historico"},
    "diagnosticos": {"criar_diagnosticos", "listar_diagnosticos", "obter_diagnosticos", "historico"},
    "evolucoes": {"criar_evolucoes", "listar_evolucoes", "obter_evolucoes", "historico"},
    "administracoes": {"criar_administracao", "listar_administracoes", "obter_administracao", "historico"},
}


def get_usuario_atual(
    request: Request,
    credenciais: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credenciais.credentials

    usuario_id, versao = ler_token_acesso(token)

    usuario = db.query(User).filter(
        User.id == usuario_id
    ).first()

    if not usuario or not usuario.ativo or usuario.versao_token != versao:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado"
        )

    request.state.usuario_id = usuario.id
    return usuario


def verificar_operacoes(db: Session, usuario: User, operacoes: tuple[str, ...]) -> None:
    if usuario.perfil != "admin" and db.scalar(select(RestricaoOperacao.id).where(
        RestricaoOperacao.usuario_id == usuario.id,
        RestricaoOperacao.operacao.in_(operacoes),
    )) is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operacao nao permitida")


def verificar_recursos(db: Session, usuario: User, operacao: str) -> None:
    if usuario.perfil == "admin":
        return
    recursos = [recurso for recurso, operacoes in OPERACOES_RECURSOS.items() if operacao in operacoes]
    if recursos and db.scalar(select(RestricaoRecurso.id).where(
        RestricaoRecurso.usuario_id == usuario.id,
        RestricaoRecurso.recurso.in_(recursos),
    )) is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recurso nao permitido")


def exigir_perfis(*perfis: str):
    def verificar(
        request: Request,
        usuario: User = Depends(get_usuario_atual),
        db: Session = Depends(get_db),
    ) -> User:
        if usuario.perfil not in perfis:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")
        verificar_operacoes(db, usuario, (request.scope["route"].name,))
        verificar_recursos(db, usuario, request.scope["route"].name)
        return usuario

    return verificar