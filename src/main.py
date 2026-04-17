from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.routes.pages import router as pages_router
from src.routes.health import router as health_router
from src.routes.uploads import router as uploads_router
from src.routes.jobs import router as jobs_router
from src.routes.collections import router as collections_router
from src.routes.query import router as query_router
from src.routes.panel import router as panel_router
from src.routes.eval import router as eval_router

app = FastAPI(title="DocuChat")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(pages_router)
app.include_router(health_router)
app.include_router(uploads_router)
app.include_router(jobs_router)
app.include_router(collections_router)
app.include_router(query_router)
app.include_router(panel_router) 
app.include_router(eval_router)