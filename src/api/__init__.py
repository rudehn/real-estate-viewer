"""The /v2 API used by the redesigned frontend."""
from fastapi import APIRouter

from api.routers import map as map_router
from api.routers import meta, search

router = APIRouter(prefix="/v2")
router.include_router(meta.router)
router.include_router(map_router.router)
router.include_router(search.router)
