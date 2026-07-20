from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import PromptCompilationRequest, PromptValidationRequest, PromptValidationResponse, ProviderPrompt
from .service import adapt_prompt, clear_prompt_cache, compile_prompt, prompt_cache_entries, template_catalog, validate_ir


router = APIRouter(prefix="/api/v1/prompts", tags=["prompt-compiler"])


@router.post("/compile")
def compile_prompt_request(
    payload: PromptCompilationRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("prompt.compile")),
):
    try:
        response = compile_prompt(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_class": "prompt_compilation_failed", "message": str(exc)}) from exc
    return api_response(response.model_dump(mode="json"), request)


@router.post("/validate")
def validate_prompt_ir(
    payload: PromptValidationRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("prompt.validate")),
):
    errors, warnings = validate_ir(payload.ir)
    response = PromptValidationResponse(valid=not errors, errors=errors, warnings=warnings)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/adapt")
def adapt_prompt_ir(
    payload: PromptValidationRequest,
    request: Request,
    provider: str = Query(default="openai"),
    _context: RequestContext = Depends(require_permission("prompt.compile")),
):
    response: ProviderPrompt = adapt_prompt(payload.ir, provider=provider)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/templates")
def list_prompt_templates(
    request: Request,
    _context: RequestContext = Depends(require_permission("prompt.view")),
):
    return collection_response(template_catalog(), request)


@router.get("/cache")
def list_prompt_cache(
    request: Request,
    _context: RequestContext = Depends(require_permission("prompt.view")),
):
    return collection_response(prompt_cache_entries(), request)


@router.delete("/cache")
def delete_prompt_cache(
    request: Request,
    prompt_id: str | None = Query(default=None),
    _context: RequestContext = Depends(require_permission("prompt.manage")),
):
    return api_response({"cleared": clear_prompt_cache(prompt_id)}, request)
