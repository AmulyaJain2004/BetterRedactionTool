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

from fastapi import APIRouter, HTTPException, Request

from api import config_editor
from api.schemas import CategoryOut, ExcludeTerm, NewRegexCategory, StructuralColumnRule

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/categories", response_model=list[CategoryOut])
def get_categories():
    return config_editor.list_categories()


@router.post("/categories", response_model=CategoryOut)
def create_category(category: NewRegexCategory, request: Request):
    try:
        config_editor.add_regex_category(
            category.name, category.patterns, category.score_threshold, category.fake_provider
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return next(c for c in config_editor.list_categories() if c["name"] == category.name)


@router.delete("/categories/{name}")
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


@router.post("/structural-columns", response_model=StructuralColumnRule)
def create_structural_column(rule: StructuralColumnRule, request: Request):
    config_editor.add_structural_column(rule.column_header, rule.category, rule.requires_any_of)
    _reload(request)
    return rule


@router.delete("/structural-columns/{index}")
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


@router.post("/exclude-list")
def create_exclude_term(entry: ExcludeTerm, request: Request):
    try:
        config_editor.add_exclude_term(entry.term)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"added": entry.term}


@router.delete("/exclude-list/{term}")
def delete_exclude_term(term: str, request: Request):
    try:
        config_editor.remove_exclude_term(term)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _reload(request)
    return {"removed": term}


def _reload(request: Request):
    request.app.state.engine.reload_categories()
