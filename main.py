from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import settings
from database import get_db
from models import EventoSeguranca
from routes.hospital import router
from routes.evolucao import router as evolucao_router
from routes.seguranca import router as seguranca_router
from routes.convenios import router as convenios_router
import uvicorn


app = FastAPI(title="Sistema Hospitalar - Prototipo", debug=settings.debug)
app.include_router(router)
app.include_router(evolucao_router)
app.include_router(seguranca_router)
app.include_router(convenios_router)
app.state.routers_permissoes = (router, evolucao_router, seguranca_router, convenios_router)


@app.middleware("http")
async def impedir_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(StarletteHTTPException)
def registrar_negacao(request: Request, exc: StarletteHTTPException):
    if exc.status_code in (401, 403, 429):
        dependency = request.app.dependency_overrides.get(get_db, get_db)
        with closing(dependency()) as gerador:
            db = next(gerador)
            route = request.scope.get("route")
            nome = getattr(route, "name", "desconhecida")
            db.add(EventoSeguranca(
                usuario_id=getattr(request.state, "usuario_id", None),
                evento="limite_login" if exc.status_code == 429 else "acesso_negado",
                operacao=str(nome)[:100],
                data_hora=datetime.now(timezone.utc),
            ))
            db.commit()
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def readiness(db: Session = Depends(get_db)) -> dict[str, str]:
    config = Config(str(Path(__file__).with_name("alembic.ini")))
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    revisao_esperada = ScriptDirectory.from_config(config).get_current_head()
    try:
        revisao = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Banco indisponivel ou nao migrado") from exc
    if revisao != revisao_esperada:
        raise HTTPException(status_code=503, detail="Banco nao esta atualizado")
    return {"status": "ready"}

if __name__ == "__main__":
    uvicorn.run("main:app", port=8000, reload=settings.debug, access_log=False, proxy_headers=False)