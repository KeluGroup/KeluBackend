from fastapi import APIRouter

from services.airtable import list_recipes_public

router = APIRouter()

VALID_LOCALES = {"es", "en", "de", "fr", "it"}


@router.get("/recetas")
def get_recetas(locale: str = "es"):
    """
    Recetas para la página web /recetas. Español viene directo de Airtable
    (fuente de verdad editable); los demás idiomas usan traducciones
    versionadas en data/recipe_translations.json.
    """
    locale = locale if locale in VALID_LOCALES else "es"
    return {"recetas": list_recipes_public(locale)}
