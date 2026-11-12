"""Settings endpoints: view/add/remove PII categories, structural table-
column rules, and ORGANIZATION deny-list entries -- the same three
customization points documented in README.md's "Customizing" section,
exposed over HTTP so the settings page (static/settings.html) can drive
them without anyone touching a YAML file.

Every mutating endpoint calls engine.reload_categories() afterward, so the
change applies to the *next* redaction job immediately -- without
restarting the server or reloading the transformer model (see that
method's docstring in redactor/engine.py for why that distinction matters).
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from api import config_editor
from api.schemas import CategoryOut, ExcludeTerm, NewRegexCategory, StructuralColumnRule
from api.settings import ALLOW_CONFIG_EDITS, PUBLIC_NOTICE

router = APIRouter(prefix="/api/config", tags=["config"])


def _require_edits_allowed():
    if not ALLOW_CONFIG_EDITS:
        raise HTTPException(403, "Settings are read-only on this deployment.")


# Applied to every POST/DELETE below; GETs stay open so the settings page
# can still show what's configured.
_EDIT = [Depends(_require_edits_allowed)]


@router.get("/status")
def get_config_status():
    return {"editable": ALLOW_CONFIG_EDITS, "public_notice": PUBLIC_NOTICE}


@router.get("/categories", response_model=list[CategoryOut])
def get_categories():
    return config_editor.list_categories()


@router.post("/categories", response_model=CategoryOut, dependencies=_EDIT)
def create_category(category: NewRegexCategory, request: Request):
    try:
        config_editor.add_regex_category(
            category.name, category.patterns, category.score_threshold, category.fake_provider
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return next(c for c in config_editor.list_categories() if c["name"] == category.name)


@router.delete("/categories/{name}", dependencies=_EDIT)
def delete_category(name: str, request: Request):
    try:
        config_editor.remove_category(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"removed": name}


@router.get("/structural-columns", response_model=list[StructuralColumnRule])
def get_structural_columns():
    return config_editor.list_structural_columns()


@router.post("/structural-columns", response_model=StructuralColumnRule, dependencies=_EDIT)
def create_structural_column(rule: StructuralColumnRule, request: Request):
    config_editor.add_structural_column(rule.column_header, rule.category, rule.requires_any_of)
    _reload(request)
    return rule


@router.delete("/structural-columns/{index}", dependencies=_EDIT)
def delete_structural_column(index: int, request: Request):
    try:
        config_editor.remove_structural_column(index)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"removed_index": index}


@router.get("/exclude-list", response_model=list[str])
def get_exclude_list():
    return config_editor.list_exclude_terms()


@router.post("/exclude-list", dependencies=_EDIT)
def create_exclude_term(entry: ExcludeTerm, request: Request):
    try:
        config_editor.add_exclude_term(entry.term)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"added": entry.term}


@router.delete("/exclude-list/{term}", dependencies=_EDIT)
def delete_exclude_term(term: str, request: Request):
    try:
        config_editor.remove_exclude_term(term)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"removed": term}


def _reload(request: Request):
    # Deferred to the start of the next job (see engine.request_reload) so
    # a running job never has its categories swapped mid-document.
    request.app.state.engine.request_reload()
