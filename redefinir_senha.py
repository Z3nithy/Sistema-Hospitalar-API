import argparse
from datetime import datetime, timezone
from getpass import getpass

from sqlalchemy import select, update

from core.senha_hash import criar_hash_senha
from database.db import SessionLocal
from models import EventoSeguranca, User


def main() -> None:
    parser = argparse.ArgumentParser(description="Redefine uma senha e revoga todas as sessoes.")
    parser.add_argument("--login", required=True)
    args = parser.parse_args()
    senha = getpass("Nova senha: ").strip()
    if senha != getpass("Confirme a senha: ").strip():
        raise SystemExit("As senhas nao conferem.")
    if not 8 <= len(senha) <= 256:
        raise SystemExit("A senha deve ter entre 8 e 256 caracteres.")
    with SessionLocal() as db:
        usuario = db.scalar(select(User).where(User.login == args.login))
        if usuario is None:
            raise SystemExit("Usuario nao encontrado.")
        db.execute(update(User).where(User.id == usuario.id).values(
            senha_hash=criar_hash_senha(senha), versao_token=User.versao_token + 1,
        ))
        db.add(EventoSeguranca(
            alvo_usuario_id=usuario.id, evento="senha_redefinida_local",
            operacao="redefinir_senha", data_hora=datetime.now(timezone.utc),
        ))
        db.commit()
    print("Senha redefinida e sessoes revogadas.")


if __name__ == "__main__":
    main()
