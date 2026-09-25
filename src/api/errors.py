"""One error shape for /v2: {"error": {"code": str, "message": str}}."""
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def _body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(_body(exc.code, exc.message), status_code=exc.status)


def _readable(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"] if p not in ("query", "path", "body"))
        parts.append(f"{where}: {err['msg']}" if where else err["msg"])
    return "; ".join(parts)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/v2"):
        return JSONResponse(_body("invalid_request", _readable(exc)), status_code=422)
    return await request_validation_exception_handler(request, exc)


async def _http_error(request: Request, exc: HTTPException):
    """Unmatched /v2 routes, wrong methods and any HTTPException, in the v2 shape."""
    if not request.url.path.startswith("/v2") or not is_body_allowed_for_status_code(
        exc.status_code
    ):
        return await http_exception_handler(request, exc)
    try:
        code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        code = "error"
    return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code,
                        headers=exc.headers)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(HTTPException, _http_error)
