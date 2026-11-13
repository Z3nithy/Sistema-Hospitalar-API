import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from sqlalchemy.engine import make_url

from core.config import settings


def banco_configurado() -> Path:
    url = make_url(settings.database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:" or url.query:
        raise ValueError("A operacao exige um banco SQLite em arquivo, sem parametros URI.")
    return Path(url.database).resolve()


def copiar_banco(origem: Path, destino: Path) -> None:
    origem = origem.resolve()
    destino = destino.resolve()
    if not origem.is_file():
        raise ValueError("O arquivo de origem nao existe.")
    if origem == destino:
        raise ValueError("Origem e destino devem ser diferentes.")
    with closing(sqlite3.connect(origem.as_uri() + "?mode=ro", uri=True)) as fonte:
        if fonte.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("O banco de origem nao passou na verificacao de integridade.")
        revisoes = fonte.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(revisoes) != 1 or not revisoes[0][0]:
            raise ValueError("O banco de origem nao possui uma revisao valida.")
        fd = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        concluido = False
        try:
            with closing(sqlite3.connect(destino)) as copia:
                fonte.backup(copia)
                if copia.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("A copia nao passou na verificacao de integridade.")
            concluido = True
        finally:
            if not concluido:
                destino.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Copia ou restaura SQLite para um arquivo novo.")
    parser.add_argument("operacao", choices=("backup", "restaurar"))
    parser.add_argument("--destino", required=True, type=Path)
    parser.add_argument("--origem", type=Path, help="Arquivo de backup, obrigatorio para restaurar.")
    args = parser.parse_args()
    if args.operacao == "backup":
        if args.origem is not None:
            parser.error("--origem nao e permitido para backup")
        origem = banco_configurado()
    else:
        if args.origem is None:
            parser.error("--origem e obrigatorio para restaurar")
        origem = args.origem
    copiar_banco(origem, args.destino)
    print("Copia criada e integridade verificada.")


if __name__ == "__main__":
    main()
