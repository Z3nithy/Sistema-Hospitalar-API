import argparse
from getpass import getpass

from sqlalchemy.exc import IntegrityError

from core.senha_hash import criar_hash_senha
from database.db import SessionLocal
from models import User
from schemas.hospital import UsuarioCriar


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria um administrador para o prototipo.")
    parser.add_argument("--nome", required=True)
    parser.add_argument("--login", required=True)
    args = parser.parse_args()
    senha = getpass("Senha: ")
    if senha != getpass("Confirme a senha: "):
        raise SystemExit("As senhas nao conferem.")
    dados = UsuarioCriar(nome=args.nome, login=args.login, senha=senha, perfil="admin")
    with SessionLocal() as db:
        db.add(User(nome=dados.nome, login=dados.login, senha_hash=criar_hash_senha(dados.senha), perfil=dados.perfil.value))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise SystemExit("Login ja cadastrado.") from exc
    print("Administrador criado.")


if __name__ == "__main__":
    main()
