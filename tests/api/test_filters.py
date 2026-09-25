import datetime as dt

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from api.errors import register_error_handlers
from api.filters import Filters, get_filters, honored

echo = FastAPI()
register_error_handlers(echo)


@echo.get("/v2/echo")
async def echo_filters(f: Filters = Depends(get_filters)):
    return {"active": f.active(), "classes": f.classes}


async def call(query: str):
    async with AsyncClient(transport=ASGITransport(app=echo), base_url="http://t") as c:
        return await c.get(f"/v2/echo?{query}")


async def test_active_filters_and_lists():
    r = await call("price_min=100000&classes=R&classes=C&neighborhood=48150000")
    assert r.status_code == 200
    assert r.json() == {"active": ["price_min", "classes", "neighborhood"], "classes": ["R", "C"]}


async def test_no_filters():
    assert (await call("")).json()["active"] == []


async def test_contradictory_filters_return_422():
    r = await call("price_min=500000&price_max=100000")
    assert r.status_code == 422
    assert r.json() == {"error": {
        "code": "invalid_filters", "message": "price_min must not be greater than price_max"
    }}


async def test_future_year_built_is_rejected():
    r = await call(f"year_built_min={dt.date.today().year + 5}")
    assert r.status_code == 422
    assert "year_built_min cannot be after" in r.json()["error"]["message"]


async def test_bad_types_use_the_v2_error_shape():
    r = await call("price_min=lots")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"
    assert "price_min" in r.json()["error"]["message"]


async def test_unknown_class_is_rejected():
    r = await call("classes=Z")
    assert r.status_code == 422


def test_honored_intersects_active_filters():
    f = Filters(price_min=1, neighborhood="X")
    assert honored(f, ["price_min", "date_from"]) == ["price_min"]
