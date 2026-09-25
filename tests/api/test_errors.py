"""/v2 answers every error in its own shape; the old routes keep FastAPI's."""


async def test_unmatched_v2_route_uses_the_v2_error_shape(client):
    r = await client.get("/v2/nope")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Not Found"}}


async def test_v2_http_errors_keep_status_and_headers(client):
    r = await client.post("/v2/meta")
    assert r.status_code == 405
    assert r.json() == {"error": {"code": "method_not_allowed",
                                  "message": "Method Not Allowed"}}
    assert r.headers["allow"] == "GET"


async def test_old_routes_keep_the_detail_shape(client):
    for path in ("/nope", "/transactions/999"):
        r = await client.get(path)
        assert r.status_code == 404
        assert r.json() == {"detail": "Not Found"}
