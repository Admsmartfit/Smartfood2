import json
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from datetime import datetime, timedelta

import models
import label_service
from database import SessionLocal, engine

# Create database tables
models.Base.metadata.create_all(bind=engine)

# ── Schema migrations (idempotent) ────────────────────────────────────────────
_MIGRATIONS = [
    "ALTER TABLE ingredients ADD COLUMN category TEXT DEFAULT 'Outros'",
    "ALTER TABLE recipes ADD COLUMN rendimento_unidades INTEGER DEFAULT 1",
    "ALTER TABLE recipes ADD COLUMN peso_porcao_g REAL DEFAULT 0.0",
    "ALTER TABLE bom_items ADD COLUMN display_unit TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN perda_desidratacao_pct REAL DEFAULT 0.0",
    "ALTER TABLE recipes ADD COLUMN markup_distribuicao REAL DEFAULT 0.0",
    # Module 5 & 6
    "ALTER TABLE ingredients ADD COLUMN current_stock REAL DEFAULT 0.0",
    "ALTER TABLE recipes ADD COLUMN current_stock_units INTEGER DEFAULT 0",
]
with engine.connect() as _conn:
    for _sql in _MIGRATIONS:
        try:
            _conn.execute(text(_sql))
            _conn.commit()
        except Exception:
            pass  # column already exists

app = FastAPI(title="SmartFood Ops 360 Foundation")

# ── Category constants (used by templates and helpers) ────────────────────────
INGREDIENT_CATEGORIES = ["Carnes", "Vegetais", "Temperos", "Laticínios", "Carboidratos", "Embalagens", "Outros"]

CAT_STYLE = {
    "Carnes":        {"emoji": "🥩", "color": "#fca5a5", "bg": "#450a0a"},
    "Vegetais":      {"emoji": "🥦", "color": "#86efac", "bg": "#052e16"},
    "Temperos":      {"emoji": "🧄", "color": "#fcd34d", "bg": "#451a03"},
    "Laticínios":    {"emoji": "🧀", "color": "#fde68a", "bg": "#422006"},
    "Carboidratos":  {"emoji": "🌾", "color": "#fdba74", "bg": "#431407"},
    "Embalagens":    {"emoji": "📦", "color": "#a5b4fc", "bg": "#1e1b4b"},
    "Outros":        {"emoji": "📋", "color": "#9ca3af", "bg": "#1f2937"},
}

# Templates setup
templates = Jinja2Templates(directory="templates")

# ── Jinja2 helpers ────────────────────────────────────────────────────────────

def _relative_time(dt: datetime | None) -> str:
    """Return a human-readable relative time string in Portuguese."""
    if dt is None:
        return "nunca"
    diff = datetime.utcnow() - dt
    if diff < timedelta(minutes=1):
        return "agora"
    if diff < timedelta(hours=1):
        m = int(diff.seconds / 60)
        return f"há {m}min"
    if diff < timedelta(days=1):
        h = int(diff.seconds / 3600)
        return f"há {h}h"
    if diff.days == 1:
        return "ontem"
    if diff.days < 7:
        return f"há {diff.days} dias"
    return dt.strftime("%d/%m/%y")

templates.env.globals["relative_time"] = _relative_time
templates.env.globals["now"] = datetime.utcnow
templates.env.globals["cat_style"] = CAT_STYLE
templates.env.globals["ingredient_categories"] = INGREDIENT_CATEGORIES

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    ingredients = db.query(models.Ingredient).order_by(models.Ingredient.name).all()
    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()
    manufacturers = db.query(models.IngredientManufacturer).order_by(models.IngredientManufacturer.brand_name).all()
    catalog = db.query(models.SupplierCatalog).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "ingredients": ingredients,
        "suppliers": suppliers,
        "manufacturers": manufacturers,
        "catalog": catalog,
    })

@app.get("/ficha-tecnica", response_class=HTMLResponse)
async def ficha_tecnica_page(request: Request, db: Session = Depends(get_db)):
    ingredients_data = []
    for ing in db.query(models.Ingredient).order_by(models.Ingredient.name).all():
        last_entry = (db.query(models.SupplierCatalog)
                      .filter_by(ingredient_id=ing.id)
                      .order_by(models.SupplierCatalog.id.desc()).first())
        ingredients_data.append({
            "id": ing.id, "name": ing.name,
            "price": last_entry.last_price if last_entry else 0.0,
            "unit": ing.unit,
        })

    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    recipes_list = [{"id": r.id, "name": r.name} for r in recipes]

    return templates.TemplateResponse("ficha_tecnica.html", {
        "request": request,
        "ingredients_json": ingredients_data,
        "recipes_list": recipes_list,
    })

# --- RECIPES ---
@app.post("/recipes")
async def create_recipe(
    name: str = Form(...), 
    description: str = Form(None), 
    labor: float = Form(0.0), 
    energy: float = Form(0.0), 
    markup: float = Form(1.0),
    db: Session = Depends(get_db)
):
    new_recipe = models.Recipe(name=name, description=description, labor_cost=labor, energy_cost=energy, markup=markup)
    db.add(new_recipe)
    db.commit()
    db.refresh(new_recipe)
    return HTMLResponse(content=f'<div class="p-4 bg-green-500/20 text-green-400 rounded">Receita "{new_recipe.name}" criada com sucesso! ID: {new_recipe.id}</div>')

# ── Helper: render rows for HTMX responses ───────────────────────────────────

def _ing_row(ing: models.Ingredient) -> str:
    n   = ing.name.replace("'", "&#39;")
    u   = ing.unit.replace("'", "&#39;")
    cat = (ing.category or "Outros").replace("'", "&#39;")
    cat_opts = "".join(
        f'<option value="{c}" {"selected" if c == (ing.category or "Outros") else ""}>{c}</option>'
        for c in INGREDIENT_CATEGORIES
    )
    return (
        f'<div id="ing-{ing.id}" class="item-row flex items-center gap-2 p-2 rounded-lg"'
        f' style="background:var(--card);border:1px solid var(--border)"'
        f' x-data="{{editing:false,n:\'{n}\',u:\'{u}\',cat:\'{cat}\'}}">'
        f'<div x-show="!editing" class="flex-1 flex items-center justify-between min-h-[44px]">'
        f'  <span class="text-sm text-white">'
        f'    <span x-text="n"></span>'
        f'    <span class="text-gray-500 text-xs"> (<span x-text="u"></span> · <span x-text="cat"></span>)</span>'
        f'  </span>'
        f'  <div class="flex gap-1">'
        f'    <button @click="editing=true" class="icon-btn hover:text-blue-400">✏️</button>'
        f'    <button hx-delete="/ingredients/{ing.id}" hx-target="#ing-{ing.id}" hx-swap="outerHTML"'
        f'            hx-confirm="Excluir \'{n}\'? Suas marcas e entradas de catálogo também serão removidas."'
        f'            class="icon-btn hover:text-red-400">🗑️</button>'
        f'  </div>'
        f'</div>'
        f'<div x-show="editing" class="flex-1 flex flex-wrap items-center gap-1.5 min-h-[44px]">'
        f'  <input x-model="n" class="field flex-1 min-w-[100px] text-sm" placeholder="Nome" />'
        f'  <input x-model="u" class="field w-14 text-sm" placeholder="un" />'
        f'  <select x-model="cat" class="field w-28 text-sm">{cat_opts}</select>'
        f'  <button @click="saveIng({ing.id},n,u,cat,$el)" class="icon-btn text-green-400 hover:text-green-300">💾</button>'
        f'  <button @click="editing=false" class="icon-btn hover:text-white">✕</button>'
        f'</div>'
        f'</div>'
    )

def _man_row(m: models.IngredientManufacturer) -> str:
    b = m.brand_name.replace("'", "&#39;")
    ing_name = m.ingredient.name if m.ingredient else ""
    return (
        f'<div id="man-{m.id}" class="item-row flex items-center gap-2 p-2 rounded-lg"'
        f' style="background:var(--card);border:1px solid var(--border)"'
        f' x-data="{{editing:false,b:\'{b}\',y:{m.yield_percentage},q:{m.quality_score},ingId:\'{m.ingredient_id}\','
        f'ingName(){{return(window.ingredientNames||{{}})[+this.ingId]||\'{ing_name}\';}}}}"'
        f' x-init="$nextTick(()=>{{const s=$el.querySelector(\'select.ing-picker\');if(s){{const nm=window.ingredientNames||{{}};Object.keys(nm).forEach(k=>{{const o=document.createElement(\'option\');o.value=k;o.textContent=nm[k];if(k==ingId)o.selected=true;s.appendChild(o);}});}}}}">'
        f'<div x-show="!editing" class="flex-1 flex items-center justify-between min-h-[44px]">'
        f'  <span class="text-sm text-white"><span x-text="b"></span>'
        f'    <span class="text-gray-500 text-xs ml-1">(<span x-text="ingName()"></span> · rend. <span x-text="y"></span>%)</span></span>'
        f'  <div class="flex gap-1">'
        f'    <button @click="editing=true" class="icon-btn hover:text-blue-400">✏️</button>'
        f'    <button hx-delete="/manufacturers/{m.id}" hx-target="#man-{m.id}" hx-swap="outerHTML"'
        f'            hx-confirm="Excluir marca \'{b}\'?"'
        f'            class="icon-btn hover:text-red-400">🗑️</button>'
        f'  </div>'
        f'</div>'
        f'<div x-show="editing" class="flex-1 flex flex-wrap items-center gap-2 min-h-[44px]">'
        f'  <select x-model="ingId" class="field w-full text-sm ing-picker"></select>'
        f'  <input x-model="b" class="field flex-1 min-w-[120px] text-sm" placeholder="Marca" />'
        f'  <input x-model="y" type="number" step="0.1" class="field w-20 text-sm" placeholder="Rend.%" />'
        f'  <input x-model="q" type="number" min="1" max="5" class="field w-14 text-sm" placeholder="★" />'
        f'  <button @click="saveMan({m.id},b,y,q,ingId,$el)" class="icon-btn text-green-400 hover:text-green-300">💾</button>'
        f'  <button @click="editing=false" class="icon-btn hover:text-white">✕</button>'
        f'</div>'
        f'</div>'
    )

def _sup_row(s: models.Supplier) -> str:
    n = s.name.replace("'", "&#39;")
    c = (s.contact_info or "").replace("'", "&#39;")
    cats = [sc.category for sc in s.supplier_categories]
    # Store as JSON in a single-quoted HTML attribute to avoid escaping issues
    cats_json = json.dumps(cats)

    # Category badges for view mode (styled by CSS [data-cat="..."] rules in index.html)
    badges = "".join(
        f'<span class="cat-badge" data-cat="{cat}">'
        f'{CAT_STYLE.get(cat, CAT_STYLE["Outros"])["emoji"]} {cat}</span>'
        for cat in cats
    )

    # Checkboxes for each category in edit mode
    checks = "".join(
        f'<label style="display:flex;align-items:center;gap:.35rem;font-size:.72rem;cursor:pointer">'
        f'<input type="checkbox" :checked="cats.includes(\'{cat}\')" '
        f'@change="cats.includes(\'{cat}\') ? cats.splice(cats.indexOf(\'{cat}\'),1) : cats.push(\'{cat}\')" />'
        f' {CAT_STYLE.get(cat, CAT_STYLE["Outros"])["emoji"]} {cat}</label>'
        for cat in INGREDIENT_CATEGORIES
    )

    confirm_msg = f"Excluir fornecedor '{n}'? Entradas de catálogo também serão removidas."
    return (
        f'<div id="sup-{s.id}" data-cats=\'{cats_json}\''
        f' class="item-row p-2 rounded-lg"'
        f' style="background:var(--card);border:1px solid var(--border)"'
        f' x-data="{{editing:false,n:\'{n}\',c:\'{c}\',cats:[]}}"'
        f' x-init="cats=JSON.parse($el.dataset.cats)">'

        # View mode
        f'<div x-show="!editing" class="flex items-start justify-between gap-2 min-h-[44px]">'
        f'  <div class="flex-1 min-w-0">'
        f'    <div class="text-sm text-white flex flex-wrap items-center gap-1">'
        f'      <span x-text="n"></span>'
        f'      <span class="text-gray-500 text-xs" x-show="c" x-text="\'· \'+c"></span>'
        f'    </div>'
        f'    <div class="flex flex-wrap gap-1 mt-1">{badges if badges else "<span style=\'font-size:.65rem;color:#6b7280\'>Sem categorias</span>"}</div>'
        f'  </div>'
        f'  <div class="flex gap-1 flex-shrink-0">'
        f'    <button @click="editing=true" class="icon-btn hover:text-blue-400">✏️</button>'
        f'    <button hx-delete="/suppliers/{s.id}" hx-target="#sup-{s.id}" hx-swap="outerHTML"'
        f'            hx-confirm="{confirm_msg}"'
        f'            class="icon-btn hover:text-red-400">🗑️</button>'
        f'  </div>'
        f'</div>'

        # Edit mode
        f'<div x-show="editing" x-cloak class="space-y-2 py-1">'
        f'  <div class="flex flex-wrap gap-1.5">'
        f'    <input x-model="n" class="field flex-1 min-w-[120px] text-sm" placeholder="Nome" />'
        f'    <input x-model="c" class="field flex-1 min-w-[120px] text-sm" placeholder="Contato" />'
        f'  </div>'
        f'  <div style="display:grid;grid-template-columns:1fr 1fr;gap:.3rem .75rem">{checks}</div>'
        f'  <div class="flex gap-2 pt-1">'
        f'    <button @click="saveSup({s.id},n,c,cats,$el)" class="icon-btn text-green-400 hover:text-green-300 text-xs">💾 Salvar</button>'
        f'    <button @click="editing=false" class="icon-btn hover:text-white text-xs">✕ Cancelar</button>'
        f'  </div>'
        f'</div>'
        f'</div>'
    )


# --- INGREDIENTS ---
@app.post("/ingredients", response_class=HTMLResponse)
async def create_ingredient(
    name: str = Form(...),
    unit: str = Form(...),
    category: str = Form("Outros"),
    db: Session = Depends(get_db),
):
    ing = models.Ingredient(name=name, unit=unit, category=category)
    db.add(ing)
    db.commit()
    db.refresh(ing)
    oob = f'<option value="{ing.id}" hx-swap-oob="beforeend:.ingredient-select">{ing.name}</option>'
    return HTMLResponse(content=_ing_row(ing) + oob, status_code=201)


@app.put("/ingredients/{ing_id}", response_class=HTMLResponse)
async def update_ingredient(
    ing_id: int,
    name: str = Form(...),
    unit: str = Form(...),
    category: str = Form("Outros"),
    db: Session = Depends(get_db),
):
    ing = db.query(models.Ingredient).filter_by(id=ing_id).first()
    if not ing:
        raise HTTPException(404)
    ing.name = name
    ing.unit = unit
    ing.category = category
    db.commit()
    return HTMLResponse("")


@app.delete("/ingredients/{ing_id}", response_class=HTMLResponse)
async def delete_ingredient(ing_id: int, db: Session = Depends(get_db)):
    # Remove dependents first (SQLite doesn't enforce FK by default)
    db.query(models.BOMItem).filter_by(ingredient_id=ing_id).delete()
    db.query(models.SupplierCatalog).filter_by(ingredient_id=ing_id).delete()
    db.query(models.IngredientManufacturer).filter_by(ingredient_id=ing_id).delete()
    ing = db.query(models.Ingredient).filter_by(id=ing_id).first()
    if ing:
        db.delete(ing)
    db.commit()
    return HTMLResponse("")


# --- MANUFACTURERS ---
@app.post("/manufacturers", response_class=HTMLResponse)
async def create_manufacturer(
    ingredient_id: int = Form(...),
    brand_name: str = Form(...),
    yield_percentage: float = Form(100.0),
    quality_score: int = Form(5),
    db: Session = Depends(get_db),
):
    m = models.IngredientManufacturer(
        ingredient_id=ingredient_id,
        brand_name=brand_name,
        yield_percentage=yield_percentage,
        quality_score=quality_score,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return HTMLResponse(content=_man_row(m), status_code=201)


@app.put("/manufacturers/{man_id}", response_class=HTMLResponse)
async def update_manufacturer(
    man_id: int,
    brand_name: str = Form(...),
    yield_percentage: float = Form(100.0),
    quality_score: int = Form(5),
    ingredient_id: int = Form(None),
    db: Session = Depends(get_db),
):
    m = db.query(models.IngredientManufacturer).filter_by(id=man_id).first()
    if not m:
        raise HTTPException(404)
    m.brand_name = brand_name
    m.yield_percentage = yield_percentage
    m.quality_score = quality_score
    if ingredient_id:
        m.ingredient_id = ingredient_id
    db.commit()
    return HTMLResponse("")


@app.delete("/manufacturers/{man_id}", response_class=HTMLResponse)
async def delete_manufacturer(man_id: int, db: Session = Depends(get_db)):
    db.query(models.SupplierCatalog).filter_by(manufacturer_id=man_id).delete()
    db.query(models.BOMItem).filter_by(manufacturer_id=man_id).update({"manufacturer_id": None})
    m = db.query(models.IngredientManufacturer).filter_by(id=man_id).first()
    if m:
        db.delete(m)
    db.commit()
    return HTMLResponse("")


# --- SUPPLIERS ---
@app.post("/suppliers", response_class=HTMLResponse)
async def create_supplier(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    name = form.get("name", "").strip()
    if not name:
        raise HTTPException(422, "Nome obrigatório")
    contact_info = form.get("contact_info") or None
    categories = form.getlist("categories")

    sup = models.Supplier(name=name, contact_info=contact_info)
    db.add(sup)
    db.flush()
    for cat in categories:
        db.add(models.SupplierCategory(supplier_id=sup.id, category=cat))
    db.commit()
    db.refresh(sup)
    oob = f'<option value="{sup.id}" hx-swap-oob="beforeend:.supplier-select">{sup.name}</option>'
    return HTMLResponse(content=_sup_row(sup) + oob, status_code=201)


@app.put("/suppliers/{sup_id}", response_class=HTMLResponse)
async def update_supplier(sup_id: int, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    name = form.get("name", "").strip()
    contact_info = form.get("contact_info") or None
    categories = form.getlist("categories")

    sup = db.query(models.Supplier).filter_by(id=sup_id).first()
    if not sup:
        raise HTTPException(404)
    sup.name = name
    sup.contact_info = contact_info
    db.query(models.SupplierCategory).filter_by(supplier_id=sup_id).delete()
    for cat in categories:
        db.add(models.SupplierCategory(supplier_id=sup_id, category=cat))
    db.commit()
    return HTMLResponse("")


@app.delete("/suppliers/{sup_id}", response_class=HTMLResponse)
async def delete_supplier(sup_id: int, db: Session = Depends(get_db)):
    db.query(models.SupplierCatalog).filter_by(supplier_id=sup_id).delete()
    sup = db.query(models.Supplier).filter_by(id=sup_id).first()
    if sup:
        db.delete(sup)
    db.commit()
    return HTMLResponse("")

# --- CATALOG ---
@app.post("/catalog")
async def add_to_catalog(
    supplier_id: int = Form(...),
    ingredient_id: int = Form(...),
    manufacturer_id: int = Form(...),
    last_price: float = Form(...),
    db: Session = Depends(get_db)
):
    new_entry = models.SupplierCatalog(
        supplier_id=supplier_id,
        ingredient_id=ingredient_id,
        manufacturer_id=manufacturer_id,
        last_price=last_price
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    return HTMLResponse(content=(
        f'<tr class="catalog-row">'
        f'<td data-label="Fornecedor" class="py-3 px-2">{new_entry.supplier.name}</td>'
        f'<td data-label="Ingrediente" class="py-3 px-2">{new_entry.ingredient.name}</td>'
        f'<td data-label="Marca" class="py-3 px-2">{new_entry.manufacturer.brand_name}</td>'
        f'<td data-label="Preço" class="py-3 px-2 text-right font-medium text-blue-300">R$ {new_entry.last_price:.2f}</td>'
        f'</tr>'
    ), status_code=201)

# --- CATALOG CRUD ---
@app.put("/catalog/{cat_id}", response_class=HTMLResponse)
async def update_catalog_price(
    cat_id: int,
    last_price: float = Form(...),
    db: Session = Depends(get_db),
):
    entry = db.query(models.SupplierCatalog).filter_by(id=cat_id).first()
    if not entry:
        raise HTTPException(404)
    entry.last_price = last_price
    entry.updated_at = datetime.utcnow()
    db.commit()
    return HTMLResponse("")


@app.delete("/catalog/{cat_id}", response_class=HTMLResponse)
async def delete_catalog(cat_id: int, db: Session = Depends(get_db)):
    entry = db.query(models.SupplierCatalog).filter_by(id=cat_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return HTMLResponse("")


# --- HTMX: Manufacturers for Ingredient ---
@app.get("/manufacturers-search", response_class=HTMLResponse)
async def search_manufacturers(ingredient_id: int, db: Session = Depends(get_db)):
    manufacturers = db.query(models.IngredientManufacturer).filter_by(ingredient_id=ingredient_id).all()
    options = "".join([f'<option value="{m.id}">{m.brand_name} (Rendimento: {m.yield_percentage}%)</option>' for m in manufacturers])
    if not manufacturers:
        return HTMLResponse(content='<option value="">Nenhuma marca cadastrada</option>')
    return HTMLResponse(content='<option value="">Selecione uma marca...</option>' + options)


# --- PREÇOS / COTAÇÕES ---
@app.get("/precos", response_class=HTMLResponse)
async def precos_page(request: Request, db: Session = Depends(get_db)):
    """
    Módulo de cotações: agrupa entradas de catálogo por ingrediente,
    com edição de preço inline e registro do tempo desde a última atualização.
    """
    ingredients = db.query(models.Ingredient).order_by(models.Ingredient.name).all()
    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()

    groups = []
    for ing in ingredients:
        entries = (
            db.query(models.SupplierCatalog)
            .filter_by(ingredient_id=ing.id)
            .order_by(models.SupplierCatalog.updated_at.desc())
            .all()
        )
        groups.append({
            "ingredient": ing,
            "entries": entries,
            "manufacturers": ing.manufacturers,
        })

    return templates.TemplateResponse("precos.html", {
        "request": request,
        "groups": groups,
        "suppliers": suppliers,
        "ingredients": ingredients,
    })


# ── Module 1 (integration): brand-aware data for Ficha Técnica ───────────────

@app.get("/api/ingredient-brands")
async def api_ingredient_brands(ingredient_id: int, db: Session = Depends(get_db)):
    """
    Return all brands for an ingredient with their yield-derived FC suggestion
    and the most-recent catalog price, so the Ficha Técnica can auto-fill
    FC and price when the user picks a specific brand.

    FC suggestion = 100 / yield_percentage  (inverse of yield).
    """
    manufacturers = (
        db.query(models.IngredientManufacturer)
        .filter_by(ingredient_id=ingredient_id)
        .all()
    )
    result = []
    for m in manufacturers:
        catalog = (
            db.query(models.SupplierCatalog)
            .filter_by(manufacturer_id=m.id)
            .order_by(models.SupplierCatalog.id.desc())
            .first()
        )
        price = catalog.last_price if catalog else 0.0
        suggested_fc = round(100.0 / m.yield_percentage, 3) if m.yield_percentage > 0 else 1.0
        result.append({
            "id": m.id,
            "brand_name": m.brand_name,
            "yield_percentage": m.yield_percentage,
            "suggested_fc": suggested_fc,
            "last_price": price,
        })
    return result


@app.get("/api/recipes")
async def list_recipes(db: Session = Depends(get_db)):
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    return [{"id": r.id, "name": r.name} for r in recipes]


@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: int, db: Session = Depends(get_db)):
    """Return full recipe state as JSON, ready to load into the Alpine editor."""
    recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(404)

    sections_data = []
    for sec in recipe.sections:
        items_data = []
        for item in sec.items:
            ing = item.ingredient
            # Resolve current catalog price for this item
            price = 0.0
            if item.manufacturer_id:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(manufacturer_id=item.manufacturer_id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price
            if price == 0.0 and ing:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(ingredient_id=ing.id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price

            # Fetch available brands for the ingredient
            brands = []
            if ing:
                for m in ing.manufacturers:
                    cat = (db.query(models.SupplierCatalog)
                           .filter_by(manufacturer_id=m.id)
                           .order_by(models.SupplierCatalog.id.desc()).first())
                    brands.append({
                        "id": m.id,
                        "brand_name": m.brand_name,
                        "yield_percentage": m.yield_percentage,
                        "suggested_fc": round(100.0 / m.yield_percentage, 3) if m.yield_percentage > 0 else 1.0,
                        "last_price": cat.last_price if cat else 0.0,
                    })

            items_data.append({
                "ingredientId":   ing.id if ing else "",
                "manufacturerId": item.manufacturer_id or "",
                "availableBrands": brands,
                "price":          price,
                "qty":            item.quantity,
                "displayUnit":    item.display_unit or "",
                "fc":             item.correction_factor,
                "fcoc":           item.cooking_factor,
            })

        sections_data.append({
            "name":      sec.name,
            "yield":     sec.post_cooking_weight,
            "instrucoes": sec.instrucoes or "",
            "items":     items_data,
        })

    return {
        "id":                  recipe.id,
        "recipeName":          recipe.name,
        "markup":              recipe.markup,
        "margemMinima":        recipe.margem_minima_pct,
        "laborCost":           recipe.labor_cost,
        "energyCost":          recipe.energy_cost,
        "observacoes":         recipe.observacoes or "",
        "rendimentoUnidades":       recipe.rendimento_unidades or 1,
        "pesoPorcaoG":              recipe.peso_porcao_g or 0.0,
        "perdaDesidratacaoPct":     recipe.perda_desidratacao_pct or 0.0,
        "markupDistribuicao":       recipe.markup_distribuicao or 0.0,
        "sections":                 sections_data,
    }


@app.delete("/recipes/{recipe_id}", response_class=HTMLResponse)
async def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
    if recipe:
        for sec in recipe.sections:
            db.query(models.BOMItem).filter_by(section_id=sec.id).delete()
        db.query(models.RecipeSection).filter_by(recipe_id=recipe_id).delete()
        db.query(models.ProductionBatch).filter_by(recipe_id=recipe_id).update({"recipe_id": None})
        db.delete(recipe)
        db.commit()
    return HTMLResponse("")


def _persist_recipe_body(body: dict, db: Session, recipe: models.Recipe):
    """Write sections + BOMItems for a recipe (replaces existing)."""
    # Delete old sections/items
    for sec in recipe.sections:
        db.query(models.BOMItem).filter_by(section_id=sec.id).delete()
    db.query(models.RecipeSection).filter_by(recipe_id=recipe.id).delete()
    db.flush()

    for sec in body.get("sections", []):
        section = models.RecipeSection(
            recipe_id=recipe.id,
            name=sec.get("name", "Seção"),
            post_cooking_weight=float(sec.get("yield", 0)),
            instrucoes=sec.get("instrucoes", ""),
        )
        db.add(section)
        db.flush()
        for it in sec.get("items", []):
            if not it.get("ingredientId"):
                continue
            db.add(models.BOMItem(
                section_id=section.id,
                ingredient_id=int(it["ingredientId"]),
                manufacturer_id=int(it["manufacturerId"]) if it.get("manufacturerId") else None,
                quantity=float(it.get("qty", 0)),
                display_unit=it.get("displayUnit", ""),
                correction_factor=float(it.get("fc", 1.0)),
                cooking_factor=float(it.get("fcoc", 1.0)),
            ))


@app.put("/recipes/{recipe_id}/full-save")
async def update_recipe(recipe_id: int, request: Request, db: Session = Depends(get_db)):
    recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(404)
    body = await request.json()
    recipe.name                = body.get("recipeName") or recipe.name
    recipe.labor_cost          = float(body.get("laborCost", 0))
    recipe.energy_cost         = float(body.get("energyCost", 0))
    recipe.markup              = float(body.get("markup", 1.0))
    recipe.margem_minima_pct   = float(body.get("margemMinima", 20.0))
    recipe.observacoes         = body.get("observacoes", "")
    recipe.rendimento_unidades     = int(body.get("rendimentoUnidades", 1))
    recipe.peso_porcao_g           = float(body.get("pesoPorcaoG", 0.0))
    recipe.perda_desidratacao_pct  = float(body.get("perdaDesidratacaoPct", 0.0))
    recipe.markup_distribuicao     = float(body.get("markupDistribuicao", 0.0))
    _persist_recipe_body(body, db, recipe)
    db.commit()
    return JSONResponse({"id": recipe.id, "name": recipe.name})


@app.post("/recipes/full-save")
async def full_save_recipe(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    recipe = models.Recipe(
        name=body.get("recipeName") or "Sem nome",
        labor_cost=float(body.get("laborCost", 0)),
        energy_cost=float(body.get("energyCost", 0)),
        markup=float(body.get("markup", 1.0)),
        margem_minima_pct=float(body.get("margemMinima", 20.0)),
        observacoes=body.get("observacoes", ""),
        rendimento_unidades=int(body.get("rendimentoUnidades", 1)),
        peso_porcao_g=float(body.get("pesoPorcaoG", 0.0)),
        perda_desidratacao_pct=float(body.get("perdaDesidratacaoPct", 0.0)),
        markup_distribuicao=float(body.get("markupDistribuicao", 0.0)),
    )
    db.add(recipe)
    db.flush()
    _persist_recipe_body(body, db, recipe)
    db.commit()
    return JSONResponse({"id": recipe.id, "name": recipe.name})


# ── Dashboard ────────────────────────────────────────────────────────────────

def _recipe_margin(recipe: models.Recipe, db: Session) -> dict:
    """
    Calculate the current margin % for a saved recipe.
    Pricing priority: brand-specific catalog price → generic ingredient catalog price.
    """
    total_ing = 0.0
    for section in recipe.sections:
        for item in section.items:
            price = 0.0
            # 1 — try brand-specific price first
            if item.manufacturer_id:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(manufacturer_id=item.manufacturer_id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price
            # 2 — fall back to any price for this ingredient
            if price == 0.0:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(ingredient_id=item.ingredient_id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price
            fcoc = item.cooking_factor if item.cooking_factor > 0 else 1.0
            total_ing += (price * item.correction_factor / fcoc) * item.quantity

    total_cost = total_ing + recipe.labor_cost + recipe.energy_cost
    suggested = total_cost * recipe.markup
    margin = ((suggested - total_cost) / suggested * 100) if suggested > 0 else 0.0
    return {
        "id": recipe.id,
        "name": recipe.name,
        "total_cost": round(total_cost, 2),
        "suggested_price": round(suggested, 2),
        "margin_pct": round(margin, 1),
        "margem_minima_pct": recipe.margem_minima_pct,
        "markup": recipe.markup,
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, limite: float = 20.0, db: Session = Depends(get_db)):
    recipes = db.query(models.Recipe).all()
    all_metrics = [_recipe_margin(r, db) for r in recipes]
    below = [m for m in all_metrics if m["margin_pct"] < limite]
    ok_list = [m for m in all_metrics if m["margin_pct"] >= limite]
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "limite": limite,
        "below_limit": below,
        "ok_list": ok_list,
        "total": len(all_metrics),
    })

# ── Bulk price update by supplier ────────────────────────────────────────────

@app.get("/precos/fornecedor", response_class=HTMLResponse)
async def get_fornecedor_precos(
    supplier_id_bulk: int = 0,
    list_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    if not supplier_id_bulk:
        return HTMLResponse("")

    supplier  = db.query(models.Supplier).filter_by(id=supplier_id_bulk).first()
    if not supplier:
        return HTMLResponse("")

    all_lists = (db.query(models.ShoppingList)
                 .order_by(models.ShoppingList.id.desc()).limit(15).all())

    if not all_lists:
        return HTMLResponse(
            "<p class='text-sm text-gray-500 py-4 text-center'>"
            "Gere uma lista em <a href='/compras' class='text-blue-400 underline'>Compras</a> primeiro "
            "para usar o motor inteligente de cotação.</p>"
        )

    curr_list = next((l for l in all_lists if l.id == list_id), all_lists[0])

    # List selector dropdown so user can switch to a previous list
    list_opts = "".join(
        f'<option value="{l.id}" {"selected" if l.id == curr_list.id else ""}>{l.name}</option>'
        for l in all_lists
    )
    html = (
        f'<div class="flex flex-col sm:flex-row sm:items-center gap-2 mb-4 p-3 rounded-xl"'
        f'     style="background:var(--bg);border:1px solid var(--border)">'
        f'  <label class="text-xs text-gray-400 whitespace-nowrap">Base de demanda:</label>'
        f'  <select name="list_id"'
        f'          hx-get="/precos/fornecedor"'
        f'          hx-include="[name=\'supplier_id_bulk\'],[name=\'list_id\']"'
        f'          hx-trigger="change"'
        f'          hx-target="#supplier-price-rows"'
        f'          class="text-sm flex-1">'
        f'    {list_opts}'
        f'  </select>'
        f'</div>'
    )

    # Cross-reference: only items whose ingredient category the supplier covers
    sup_cats    = {sc.category for sc in supplier.supplier_categories}
    list_items  = [i for i in curr_list.items
                   if i.ingredient and (i.ingredient.category or "Outros") in sup_cats]

    if not list_items:
        html += (
            f"<p class='text-sm text-gray-500 py-3'>"
            f"<strong>{supplier.name}</strong> não tem categorias compatíveis com esta lista. "
            f"Configure as categorias do fornecedor em "
            f"<a href='/' class='text-blue-400 underline'>Cadastros</a>.</p>"
        )
        return HTMLResponse(html)

    rows = ""
    for li in sorted(list_items, key=lambda x: x.ingredient.name):
        ing   = li.ingredient
        # Last known price/brand from this supplier for this ingredient
        cat   = (db.query(models.SupplierCatalog)
                 .filter_by(supplier_id=supplier_id_bulk, ingredient_id=ing.id)
                 .order_by(models.SupplierCatalog.id.desc()).first())
        last_price = cat.last_price if cat else ""
        brand_id   = cat.manufacturer_id if cat else ""
        brands     = db.query(models.IngredientManufacturer).filter_by(ingredient_id=ing.id).all()
        brand_opts = "".join(
            f'<option value="{b.id}" {"selected" if brand_id == b.id else ""}>{b.brand_name}</option>'
            for b in brands
        )
        badge = CAT_STYLE.get(ing.category or "Outros", CAT_STYLE["Outros"])
        rows += (
            f'<div class="flex flex-col sm:flex-row sm:items-center gap-3 py-3'
            f'            border-b border-gray-800 last:border-0">'
            f'  <div class="flex-1 min-w-0">'
            f'    <div class="flex items-center gap-2 flex-wrap">'
            f'      <span class="text-sm font-medium text-white">{ing.name}</span>'
            f'      <span class="cat-badge" data-cat="{ing.category or "Outros"}">'
            f'        {badge["emoji"]} {ing.category or "Outros"}'
            f'      </span>'
            f'      <span class="text-xs text-blue-400">{li.qty:.3f} {ing.unit}</span>'
            f'    </div>'
            f'    <input type="hidden" name="ingredient_ids" value="{ing.id}" />'
            f'    <select name="manufacturer_ids" class="text-xs mt-1 w-full sm:w-64">'
            f'      <option value="">Qual a marca ofertada?</option>'
            f'      {brand_opts}'
            f'    </select>'
            f'  </div>'
            f'  <div class="flex items-center gap-2 flex-shrink-0">'
            f'    <div class="text-right hidden sm:block">'
            f'      <p class="text-xs text-gray-500">Último:</p>'
            f'      <p class="text-sm text-gray-400 font-mono">R$ {last_price if last_price != "" else "—"}</p>'
            f'    </div>'
            f'    <div class="flex items-center gap-1">'
            f'      <span class="text-gray-500 text-sm">R$</span>'
            f'      <input type="number" name="prices" step="0.01" min="0"'
            f'             value="{last_price if last_price != "" else ""}"'
            f'             placeholder="Novo preço"'
            f'             class="w-28 text-right font-mono text-sm" style="color:#93c5fd;min-height:36px" />'
            f'    </div>'
            f'  </div>'
            f'</div>'
        )

    html += (
        f'<div class="rounded-xl px-4 py-1 mt-2"'
        f'     style="background:var(--bg);border:1px solid var(--border)">'
        f'  {rows}'
        f'</div>'
        f'<button type="submit" class="btn btn-primary btn-full mt-4 text-sm">'
        f'  💾 Salvar cotação — {len(list_items)} item{"ns" if len(list_items) != 1 else ""}'
        f'</button>'
    )
    return HTMLResponse(html)


@app.post("/precos/bulk-update", response_class=HTMLResponse)
async def bulk_update_precos(request: Request, db: Session = Depends(get_db)):
    form           = await request.form()
    supplier_id    = int(form.get("supplier_id_bulk", 0) or 0)
    ingredient_ids = form.getlist("ingredient_ids")
    manufacturer_ids = form.getlist("manufacturer_ids")
    prices         = form.getlist("prices")

    updated = 0
    for i_id, m_id, price_str in zip(ingredient_ids, manufacturer_ids, prices):
        if not m_id or not price_str:
            continue
        try:
            price = float(price_str)
            entry = (db.query(models.SupplierCatalog)
                     .filter_by(supplier_id=supplier_id,
                                ingredient_id=int(i_id),
                                manufacturer_id=int(m_id)).first())
            if entry:
                entry.last_price = price
                entry.updated_at = datetime.utcnow()
            else:
                db.add(models.SupplierCatalog(
                    supplier_id=supplier_id,
                    ingredient_id=int(i_id),
                    manufacturer_id=int(m_id),
                    last_price=price,
                ))
            updated += 1
        except (ValueError, TypeError):
            pass
    db.commit()
    return HTMLResponse(
        f'<div class="p-3 rounded-lg text-sm text-green-300 mt-3 flex items-center gap-2"'
        f' style="background:rgba(22,101,52,.25);border:1px solid rgba(34,197,94,.2)">'
        f'  ✓ {updated} item{"ns" if updated != 1 else ""} atualizado{"s" if updated != 1 else ""} com sucesso!'
        f'</div>'
    )


# ── Module 3: Shopping list / Compras ────────────────────────────────────────

@app.get("/compras", response_class=HTMLResponse)
async def compras_page(request: Request, db: Session = Depends(get_db)):
    recipes  = db.query(models.Recipe).order_by(models.Recipe.name).all()
    return templates.TemplateResponse("compras.html", {
        "request": request,
        "recipes": recipes,
    })


@app.post("/api/shopping-list", response_class=HTMLResponse)
async def generate_shopping_list(request: Request, db: Session = Depends(get_db)):
    """
    Body: [{"recipe_id": 1, "portions": 50, "recipe_name": "..."}, ...]
    Returns an HTML fragment grouped by ingredient category.
    """
    body = await request.json()

    # Aggregate: ingredient_id → totals
    agg: dict[int, dict] = {}
    for entry in body:
        recipe_id = int(entry.get("recipe_id", 0))
        portions  = float(entry.get("portions", 1) or 1)
        recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
        if not recipe:
            continue
        for section in recipe.sections:
            for item in section.items:
                ing = item.ingredient
                if not ing:
                    continue
                qty_bruto = item.quantity * item.correction_factor * portions
                if ing.id not in agg:
                    agg[ing.id] = {
                        "name":     ing.name,
                        "unit":     ing.unit,
                        "category": ing.category or "Outros",
                        "qty":      0.0,
                    }
                agg[ing.id]["qty"] += qty_bruto

    if not agg:
        return HTMLResponse(
            '<p class="text-gray-500 text-sm py-6 text-center">Nenhum insumo encontrado nas receitas selecionadas.</p>'
        )

    # Auto-save this shopping list so /precos can cross-reference it
    save_banner = ""
    try:
        s_list = models.ShoppingList(
            name=f"Lista gerada em {datetime.utcnow().strftime('%d/%m/%Y às %H:%M')}"
        )
        db.add(s_list)
        db.flush()
        for ing_id, data in agg.items():
            db.add(models.ShoppingListItem(
                list_id=s_list.id, ingredient_id=ing_id, qty=data["qty"]
            ))
        db.commit()
        save_banner = (
            f'<div class="mb-4 px-3 py-2 rounded-lg text-xs text-green-300 flex items-center gap-2"'
            f'     style="background:rgba(22,101,52,.25);border:1px solid rgba(34,197,94,.2)">'
            f'  ✓ Lista salva automaticamente — use em <a href="/precos" class="underline text-green-200">Cotações</a>'
            f'  para cruzar com fornecedores.'
            f'</div>'
        )
    except Exception as exc:
        db.rollback()
        save_banner = (
            f'<div class="mb-4 px-3 py-2 rounded-lg text-xs text-yellow-300 flex items-center gap-2"'
            f'     style="background:rgba(120,53,15,.25);border:1px solid rgba(234,179,8,.2)">'
            f'  ⚠ Lista gerada mas não salva no banco: {exc}. '
            f'  Reinicie o servidor para criar as tabelas novas.'
            f'</div>'
        )

    # Group by category in a defined order
    CAT_ORDER = ["Carnes", "Vegetais", "Temperos", "Laticínios", "Carboidratos", "Embalagens", "Outros"]
    grouped: dict[str, list] = {c: [] for c in CAT_ORDER}
    for item in agg.values():
        cat = item["category"] if item["category"] in grouped else "Outros"
        grouped[cat].append(item)

    # Build HTML
    html_parts: list[str] = []
    for cat in CAT_ORDER:
        items = sorted(grouped[cat], key=lambda x: x["name"])
        if not items:
            continue
        rows = "".join(
            f'<li class="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0">'
            f'  <input type="checkbox" class="w-4 h-4 accent-blue-600 flex-shrink-0" />'
            f'  <span class="flex-1 text-gray-900 text-sm">{i["name"]}</span>'
            f'  <span class="font-bold text-gray-900 text-sm tabular-nums">{i["qty"]:.3f}</span>'
            f'  <span class="text-gray-500 text-xs w-6">{i["unit"]}</span>'
            f'</li>'
            for i in items
        )
        html_parts.append(
            f'<div class="mb-5">'
            f'  <h3 class="text-xs font-bold text-gray-500 uppercase tracking-widest mb-2 flex items-center gap-2">'
            f'    <span>{_cat_icon(cat)}</span> {cat}'
            f'    <span class="ml-auto text-gray-400 font-normal normal-case">{len(items)} item{"s" if len(items) != 1 else ""}</span>'
            f'  </h3>'
            f'  <ul class="bg-white rounded-xl border border-gray-200 px-4 divide-y divide-gray-100">{rows}</ul>'
            f'</div>'
        )
    return HTMLResponse(save_banner + "".join(html_parts))


def _cat_icon(cat: str) -> str:
    return {
        "Carnes": "🥩", "Vegetais": "🥦", "Temperos": "🧄",
        "Laticínios": "🧀", "Carboidratos": "🌾",
        "Embalagens": "📦", "Outros": "📋",
    }.get(cat, "📋")


# ── Module 2: Labels ──────────────────────────────────────────────────────────

@app.get("/labels", response_class=HTMLResponse)
async def labels_page(request: Request, db: Session = Depends(get_db)):
    label_templates = db.query(models.LabelTemplate).all()
    batches = (
        db.query(models.ProductionBatch)
        .order_by(models.ProductionBatch.production_date.desc())
        .limit(50)
        .all()
    )
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()

    # Build filtered ingredients list per recipe (Carnes, Laticínios, Carboidratos only)
    allowed_cats = {"Carnes", "Laticínios", "Carboidratos"}
    recipes_ingredients: dict[int, str] = {}
    for r in recipes:
        seen: list[str] = []
        for sec in r.sections:
            for item in sec.items:
                ing = item.ingredient
                if ing and ing.category in allowed_cats and ing.name not in seen:
                    seen.append(ing.name)
        recipes_ingredients[r.id] = ", ".join(seen)

    # Serialise for Alpine.js consumption
    templates_json = [
        {
            "id": t.id,
            "name": t.name,
            "width_mm": t.width_mm,
            "height_mm": t.height_mm,
            "printer_type": t.printer_type,
            "printer_ip": t.printer_ip or "",
            "printer_port": t.printer_port,
            "fields_config": t.fields_config,
        }
        for t in label_templates
    ]
    batches_json = [
        {
            "id": b.id,
            "batch_number": b.batch_number,
            "product_name": b.product_name,
            "production_date": b.production_date.strftime("%d/%m/%Y"),
            "expiry_date": b.expiry_date.strftime("%d/%m/%Y"),
            "weight_kg": b.weight_kg,
            "ingredients_summary": b.ingredients_summary,
        }
        for b in batches
    ]
    return templates.TemplateResponse("labels.html", {
        "request": request,
        "label_templates": label_templates,
        "batches": batches,
        "recipes": recipes,
        "templates_json": templates_json,
        "batches_json": batches_json,
        "recipes_ingredients": recipes_ingredients,
    })


@app.post("/labels")
async def create_label_template(
    name: str = Form(...),
    width_mm: float = Form(62.0),
    height_mm: float = Form(40.0),
    printer_type: str = Form("ZPL"),
    printer_ip: str = Form(""),
    printer_port: int = Form(9100),
    fields_config: str = Form("[]"),
    db: Session = Depends(get_db),
):
    tpl = models.LabelTemplate(
        name=name,
        width_mm=width_mm,
        height_mm=height_mm,
        printer_type=printer_type.upper(),
        printer_ip=printer_ip,
        printer_port=printer_port,
        fields_config=fields_config,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return JSONResponse({
        "id": tpl.id, "name": tpl.name,
        "width_mm": tpl.width_mm, "height_mm": tpl.height_mm,
        "printer_type": tpl.printer_type,
        "printer_ip": tpl.printer_ip or "",
        "printer_port": tpl.printer_port,
        "fields_config": tpl.fields_config,
    }, status_code=201)


@app.delete("/labels/{template_id}", response_class=HTMLResponse)
async def delete_label_template(template_id: int, db: Session = Depends(get_db)):
    db.query(models.ProductionBatch).filter_by(label_template_id=template_id).update({"label_template_id": None})
    tpl = db.query(models.LabelTemplate).filter_by(id=template_id).first()
    if tpl:
        db.delete(tpl)
        db.commit()
    return HTMLResponse("")


@app.put("/labels/{template_id}")
async def update_label_template(
    template_id: int,
    name: str = Form(...),
    width_mm: float = Form(62.0),
    height_mm: float = Form(40.0),
    printer_type: str = Form("ZPL"),
    printer_ip: str = Form(""),
    printer_port: int = Form(9100),
    fields_config: str = Form("[]"),
    db: Session = Depends(get_db),
):
    tpl = db.query(models.LabelTemplate).filter_by(id=template_id).first()
    if not tpl:
        raise HTTPException(404)
    tpl.name = name
    tpl.width_mm = width_mm
    tpl.height_mm = height_mm
    tpl.printer_type = printer_type.upper()
    tpl.printer_ip = printer_ip
    tpl.printer_port = printer_port
    tpl.fields_config = fields_config
    db.commit()
    return JSONResponse({
        "id": tpl.id, "name": tpl.name,
        "width_mm": tpl.width_mm, "height_mm": tpl.height_mm,
        "printer_type": tpl.printer_type,
        "printer_ip": tpl.printer_ip or "",
        "printer_port": tpl.printer_port,
        "fields_config": tpl.fields_config,
    })


@app.get("/labels/{template_id}/preview", response_class=HTMLResponse)
async def label_preview(
    template_id: int,
    request: Request,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    tpl = db.query(models.LabelTemplate).filter_by(id=template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    template_data = {
        "width_mm": tpl.width_mm,
        "height_mm": tpl.height_mm,
        "fields_config": tpl.fields_config,
    }

    if batch_id:
        batch = db.query(models.ProductionBatch).filter_by(id=batch_id).first()
        batch_data = {
            "id": batch.id,
            "product_name": batch.product_name,
            "batch_number": batch.batch_number,
            "production_date": batch.production_date,
            "expiry_date": batch.expiry_date,
            "weight_kg": batch.weight_kg,
            "ingredients_summary": batch.ingredients_summary,
        } if batch else {}
    else:
        batch_data = {
            "id": 0,
            "product_name": "Frango Grelhado",
            "batch_number": "L-2024-001",
            "production_date": datetime.utcnow(),
            "expiry_date": datetime.utcnow(),
            "weight_kg": 0.350,
            "ingredients_summary": "Frango, Alho, Azeite, Sal",
        }

    base_url = str(request.base_url)
    print_data = label_service._build_print_data(batch_data, base_url)
    html = label_service.generate_preview_html(template_data, print_data)
    return HTMLResponse(content=html)


@app.get("/labels/{template_id}/command", response_class=HTMLResponse)
async def label_command(
    template_id: int,
    request: Request,
    batch_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """Return the raw ZPL/TSPL command string (useful for debugging)."""
    tpl = db.query(models.LabelTemplate).filter_by(id=template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")

    template_data = {
        "width_mm": tpl.width_mm,
        "height_mm": tpl.height_mm,
        "fields_config": tpl.fields_config,
    }

    if batch_id:
        batch = db.query(models.ProductionBatch).filter_by(id=batch_id).first()
        batch_data = {
            "id": batch.id if batch else 0,
            "product_name": getattr(batch, "product_name", ""),
            "batch_number": getattr(batch, "batch_number", ""),
            "production_date": getattr(batch, "production_date", datetime.utcnow()),
            "expiry_date": getattr(batch, "expiry_date", datetime.utcnow()),
            "weight_kg": getattr(batch, "weight_kg", 0.0),
            "ingredients_summary": getattr(batch, "ingredients_summary", ""),
        }
    else:
        batch_data = {"id": 0, "product_name": "Exemplo", "batch_number": "L-000",
                      "production_date": datetime.utcnow(), "expiry_date": datetime.utcnow(),
                      "weight_kg": 0.0, "ingredients_summary": ""}

    base_url = str(request.base_url)
    print_data = label_service._build_print_data(batch_data, base_url)

    if tpl.printer_type == "TSPL":
        cmd = label_service.generate_tspl(template_data, print_data)
    else:
        cmd = label_service.generate_zpl(template_data, print_data)

    escaped = cmd.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return HTMLResponse(
        content=f'<pre class="text-xs text-green-300 bg-gray-900 p-3 rounded overflow-x-auto whitespace-pre-wrap">{escaped}</pre>'
    )


@app.post("/labels/{template_id}/print", response_class=HTMLResponse)
async def print_label(
    template_id: int,
    request: Request,
    batch_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
):
    tpl = db.query(models.LabelTemplate).filter_by(id=template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    batch = db.query(models.ProductionBatch).filter_by(id=batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    template_data = {
        "width_mm": tpl.width_mm,
        "height_mm": tpl.height_mm,
        "fields_config": tpl.fields_config,
    }
    batch_data = {
        "id": batch.id,
        "product_name": batch.product_name,
        "batch_number": batch.batch_number,
        "production_date": batch.production_date,
        "expiry_date": batch.expiry_date,
        "weight_kg": batch.weight_kg,
        "ingredients_summary": batch.ingredients_summary,
    }

    base_url = str(request.base_url)
    print_data = label_service._build_print_data(batch_data, base_url)

    if tpl.printer_type == "TSPL":
        cmd = label_service.generate_tspl(template_data, print_data, quantity)
    else:
        cmd = label_service.generate_zpl(template_data, print_data, quantity)

    if not tpl.printer_ip:
        return HTMLResponse(
            content='<div class="p-3 bg-yellow-500/20 text-yellow-300 rounded text-sm">⚠️ IP da impressora não configurado no template.</div>'
        )

    ok, msg = label_service.send_to_printer(tpl.printer_ip, tpl.printer_port, cmd)
    css = "green" if ok else "red"
    icon = "✅" if ok else "❌"
    return HTMLResponse(
        content=f'<div class="p-3 bg-{css}-500/20 text-{css}-300 rounded text-sm">{icon} {msg}</div>'
    )


# ── Module 2: Batches ─────────────────────────────────────────────────────────

@app.post("/batches", response_class=HTMLResponse)
async def create_batch(
    batch_number: str = Form(...),
    product_name: str = Form(...),
    expiry_date: str = Form(...),        # ISO date string: YYYY-MM-DD
    weight_kg: float = Form(0.0),
    ingredients_summary: str = Form(""),
    tutorial_url: str = Form(""),
    promo_url: str = Form(""),
    label_template_id: Optional[int] = Form(None),
    recipe_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    expiry_dt = datetime.fromisoformat(expiry_date)
    batch = models.ProductionBatch(
        batch_number=batch_number,
        product_name=product_name,
        expiry_date=expiry_dt,
        weight_kg=weight_kg,
        ingredients_summary=ingredients_summary,
        tutorial_url=tutorial_url,
        promo_url=promo_url,
        label_template_id=label_template_id or None,
        recipe_id=recipe_id or None,
    )
    db.add(batch)
    db.flush()

    # ── Auto stock-in: increment frozen product count ────────────────────────
    if recipe_id:
        recipe_obj = db.query(models.Recipe).filter_by(id=recipe_id).first()
        if recipe_obj:
            units = max(1, recipe_obj.rendimento_unidades or 1)
            recipe_obj.current_stock_units = (recipe_obj.current_stock_units or 0) + units
            db.add(models.StockMovement(
                type="IN", item_type="PRODUCT", item_id=recipe_id,
                quantity=units,
                description=f"Produção Lote {batch_number}",
            ))

    db.commit()
    db.refresh(batch)
    expiry_str = batch.expiry_date.strftime("%d/%m/%Y")
    return HTMLResponse(
        content=(
            f'<tr id="batch-{batch.id}" class="border-b border-gray-700 text-sm">'
            f'<td class="py-2 px-3 text-gray-200">{batch.batch_number}</td>'
            f'<td class="py-2 px-3 text-gray-200">{batch.product_name}</td>'
            f'<td class="py-2 px-3 text-gray-400">{expiry_str}</td>'
            f'<td class="py-2 px-3">'
            f'  <a href="/qr/{batch.id}" target="_blank" '
            f'     class="text-xs text-blue-400 underline">QR ↗</a>'
            f'</td>'
            f'</tr>'
        ),
        status_code=201,
    )


# ── Module 2: Dynamic QR redirect ────────────────────────────────────────────

@app.get("/qr/{batch_id}")
async def qr_redirect(batch_id: int, db: Session = Depends(get_db)):
    """
    Dynamic QR Code endpoint.
    • Within PROMO_DAYS_BEFORE_EXPIRY days of expiry → redirect to promo_url
    • Otherwise                                       → redirect to tutorial_url
    """
    batch = db.query(models.ProductionBatch).filter_by(id=batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Lote não encontrado")

    url = label_service.resolve_qr_url(
        batch.expiry_date,
        batch.tutorial_url,
        batch.promo_url,
    )
    return RedirectResponse(url=url, status_code=302)


# ── Module 5: Estoque ────────────────────────────────────────────────────────

@app.get("/estoque", response_class=HTMLResponse)
async def estoque_page(request: Request, db: Session = Depends(get_db)):
    ingredients = db.query(models.Ingredient).order_by(models.Ingredient.name).all()
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    movements = (
        db.query(models.StockMovement)
        .order_by(models.StockMovement.date.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse("estoque.html", {
        "request": request,
        "ingredients": ingredients,
        "recipes": recipes,
        "movements": movements,
        "active_page": "estoque",
    })


@app.post("/api/stock/adjust", response_class=HTMLResponse)
async def stock_adjust(
    item_type: str = Form(...),   # INGREDIENT or PRODUCT
    item_id: int = Form(...),
    quantity: float = Form(...),  # positive = IN, negative = OUT
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    move_type = "IN" if quantity >= 0 else "OUT"
    abs_qty = abs(quantity)

    if item_type == "INGREDIENT":
        ing = db.query(models.Ingredient).filter_by(id=item_id).first()
        if not ing:
            raise HTTPException(404)
        ing.current_stock = max(0.0, (ing.current_stock or 0.0) + quantity)
        db.add(models.StockMovement(
            type=move_type, item_type="INGREDIENT", item_id=item_id,
            quantity=abs_qty, description=description or f"Ajuste manual",
        ))
        db.commit()
        return HTMLResponse(
            f'<span class="font-mono text-blue-300">{ing.current_stock:.3f}</span>',
            headers={"HX-Trigger": '{"showToast":{"msg":"Estoque atualizado","type":"success"}}'},
        )
    else:
        recipe = db.query(models.Recipe).filter_by(id=item_id).first()
        if not recipe:
            raise HTTPException(404)
        recipe.current_stock_units = max(0, (recipe.current_stock_units or 0) + int(quantity))
        db.add(models.StockMovement(
            type=move_type, item_type="PRODUCT", item_id=item_id,
            quantity=abs_qty, description=description or f"Ajuste manual",
        ))
        db.commit()
        return HTMLResponse(
            f'<span class="font-mono text-blue-300">{recipe.current_stock_units}</span>',
            headers={"HX-Trigger": '{"showToast":{"msg":"Estoque atualizado","type":"success"}}'},
        )


# ── Module 6: Clientes ───────────────────────────────────────────────────────

def _customer_row(c: models.Customer, orders: list) -> str:
    """Render one customer accordion row (view + order history)."""
    n = c.name.replace("'", "&#39;")
    ph = (c.phone or "").replace("'", "&#39;")
    em = (c.email or "").replace("'", "&#39;")
    addr = (c.address or "").replace("'", "&#39;")
    order_rows = ""
    for o in orders:
        status_color = {
            "PENDING": "#fcd34d",
            "DELIVERED": "#86efac",
            "CANCELED": "#fca5a5",
        }.get(o.status, "#9ca3af")
        status_label = {
            "PENDING": "Pendente",
            "DELIVERED": "Entregue",
            "CANCELED": "Cancelado",
        }.get(o.status, o.status)
        items_txt = ", ".join(
            f"{oi.recipe.name if oi.recipe else '?'} x{oi.quantity}"
            for oi in o.items
        )
        order_rows += (
            f'<div class="flex flex-wrap items-center gap-2 py-2 border-b border-gray-800 last:border-0 text-xs">'
            f'  <span class="text-gray-400">{o.order_date.strftime("%d/%m/%Y")}</span>'
            f'  <span class="flex-1 text-gray-300">{items_txt or "—"}</span>'
            f'  <span class="font-mono text-blue-300">R$ {o.total_amount:.2f}</span>'
            f'  <span class="px-2 py-0.5 rounded-full text-xs font-medium"'
            f'        style="color:{status_color};background:{status_color}22">{status_label}</span>'
            f'</div>'
        )
    if not order_rows:
        order_rows = '<p class="text-xs text-gray-500 py-2">Nenhum pedido ainda.</p>'

    return (
        f'<div id="cust-{c.id}" class="card p-0 overflow-hidden"'
        f' x-data="{{open:false,editing:false,n:\'{n}\',ph:\'{ph}\',em:\'{em}\',addr:\'{addr}\'}}">'
        # Header
        f'<div class="flex items-center gap-3 px-4 py-3 cursor-pointer" @click="open=!open">'
        f'  <span class="text-blue-400 text-base">👤</span>'
        f'  <div class="flex-1 min-w-0">'
        f'    <p class="text-sm font-medium text-white" x-text="n"></p>'
        f'    <p class="text-xs text-gray-400" x-text="(ph ? ph : \'\') + (em ? \' · \'+em : \'\')"></p>'
        f'  </div>'
        f'  <span class="text-xs text-gray-500">{len(orders)} pedido{"s" if len(orders) != 1 else ""}</span>'
        f'  <span class="text-gray-500 text-sm" x-text="open ? \'▲\' : \'▼\'"></span>'
        f'</div>'
        # Accordion body
        f'<div x-show="open" x-cloak class="border-t border-gray-700 px-4 py-3 space-y-3">'
        # Edit form (inline)
        f'  <div x-show="editing" x-cloak class="space-y-2 pb-3 border-b border-gray-700">'
        f'    <div class="grid grid-cols-2 gap-2">'
        f'      <input x-model="n" class="field text-sm" placeholder="Nome" />'
        f'      <input x-model="ph" class="field text-sm" placeholder="Telefone" />'
        f'      <input x-model="em" class="field text-sm" placeholder="E-mail" />'
        f'      <input x-model="addr" class="field text-sm" placeholder="Endereço" />'
        f'    </div>'
        f'    <div class="flex gap-2">'
        f'      <button @click="editing=false;saveCust({c.id},n,ph,em,addr)" class="btn btn-primary btn-sm">💾 Salvar</button>'
        f'      <button @click="editing=false" class="btn btn-secondary btn-sm">Cancelar</button>'
        f'    </div>'
        f'  </div>'
        # View actions
        f'  <div x-show="!editing" class="flex gap-2 flex-wrap text-xs text-gray-400">'
        f'    <span x-show="addr" x-text="\'📍 \'+addr"></span>'
        f'    <button @click="editing=true" class="btn btn-secondary btn-sm ml-auto">✏️ Editar</button>'
        f'    <button hx-delete="/clientes/{c.id}" hx-target="#cust-{c.id}" hx-swap="outerHTML"'
        f'            hx-confirm="Excluir {n}? Os pedidos também serão removidos."'
        f'            class="btn btn-danger btn-sm">🗑️</button>'
        f'  </div>'
        # Order history
        f'  <div>'
        f'    <p class="text-xs font-semibold text-gray-400 mb-1 uppercase tracking-wide">Histórico de Pedidos</p>'
        f'    {order_rows}'
        f'  </div>'
        f'</div>'
        f'</div>'
    )


@app.get("/clientes", response_class=HTMLResponse)
async def clientes_page(request: Request, db: Session = Depends(get_db)):
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    return templates.TemplateResponse("clientes.html", {
        "request": request,
        "customers": customers,
        "active_page": "clientes",
    })


@app.post("/clientes", response_class=HTMLResponse)
async def create_customer(
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
):
    c = models.Customer(name=name, phone=phone, email=email, address=address)
    db.add(c)
    db.commit()
    db.refresh(c)
    return HTMLResponse(content=_customer_row(c, []), status_code=201)


@app.put("/clientes/{cust_id}", response_class=HTMLResponse)
async def update_customer(
    cust_id: int,
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
):
    c = db.query(models.Customer).filter_by(id=cust_id).first()
    if not c:
        raise HTTPException(404)
    c.name = name
    c.phone = phone
    c.email = email
    c.address = address
    db.commit()
    return HTMLResponse("")


@app.delete("/clientes/{cust_id}", response_class=HTMLResponse)
async def delete_customer(cust_id: int, db: Session = Depends(get_db)):
    c = db.query(models.Customer).filter_by(id=cust_id).first()
    if c:
        db.delete(c)
        db.commit()
    return HTMLResponse("")


# ── Module 6: Pedidos ────────────────────────────────────────────────────────

def _recipe_sale_price(recipe: models.Recipe, db: Session) -> float:
    """Compute suggested sale price per unit using current costs + markup."""
    total_ing = 0.0
    for sec in recipe.sections:
        for item in sec.items:
            price = 0.0
            if item.manufacturer_id:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(manufacturer_id=item.manufacturer_id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price
            if price == 0.0:
                c = (db.query(models.SupplierCatalog)
                     .filter_by(ingredient_id=item.ingredient_id)
                     .order_by(models.SupplierCatalog.id.desc()).first())
                if c:
                    price = c.last_price
            fcoc = item.cooking_factor if item.cooking_factor > 0 else 1.0
            total_ing += (price * item.correction_factor / fcoc) * item.quantity
    total_cost = total_ing + recipe.labor_cost + recipe.energy_cost
    units = max(1, recipe.rendimento_unidades or 1)
    return round(total_cost * (recipe.markup or 1.0) / units, 2)


@app.get("/pedidos", response_class=HTMLResponse)
async def pedidos_page(request: Request, db: Session = Depends(get_db)):
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    recipes_data = []
    for r in recipes:
        recipes_data.append({
            "id": r.id,
            "name": r.name,
            "stock": r.current_stock_units or 0,
            "price": _recipe_sale_price(r, db),
        })
    orders = (
        db.query(models.SalesOrder)
        .order_by(models.SalesOrder.order_date.desc())
        .limit(30)
        .all()
    )
    return templates.TemplateResponse("pedidos.html", {
        "request": request,
        "customers": customers,
        "recipes_data": recipes_data,
        "orders": orders,
        "active_page": "pedidos",
    })


@app.post("/orders")
async def create_order(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    customer_id = int(body.get("customer_id", 0))
    items = body.get("items", [])
    notes = body.get("notes", "")

    if not customer_id:
        raise HTTPException(422, "Cliente obrigatório")
    if not items:
        raise HTTPException(422, "Adicione ao menos um produto")

    customer = db.query(models.Customer).filter_by(id=customer_id).first()
    if not customer:
        raise HTTPException(404, "Cliente não encontrado")

    total = 0.0
    order = models.SalesOrder(
        customer_id=customer_id,
        status="PENDING",
        notes=notes,
    )
    db.add(order)
    db.flush()

    for it in items:
        recipe_id = int(it.get("recipe_id", 0))
        qty = int(it.get("quantity", 1))
        unit_price = float(it.get("unit_price", 0))
        recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
        if not recipe or qty <= 0:
            continue
        db.add(models.SalesOrderItem(
            order_id=order.id,
            recipe_id=recipe_id,
            quantity=qty,
            unit_price=unit_price,
        ))
        total += qty * unit_price

    order.total_amount = round(total, 2)
    db.commit()
    db.refresh(order)
    return JSONResponse({"id": order.id, "total": order.total_amount, "status": order.status})


@app.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    body = await request.json()
    new_status = body.get("status", "")
    if new_status not in ("PENDING", "DELIVERED", "CANCELED"):
        raise HTTPException(422, "Status inválido")

    order = db.query(models.SalesOrder).filter_by(id=order_id).first()
    if not order:
        raise HTTPException(404)

    old_status = order.status
    order.status = new_status

    # When delivering: deduct stock and log movements
    if new_status == "DELIVERED" and old_status != "DELIVERED":
        for oi in order.items:
            recipe = db.query(models.Recipe).filter_by(id=oi.recipe_id).first()
            if recipe:
                recipe.current_stock_units = max(0, (recipe.current_stock_units or 0) - oi.quantity)
                db.add(models.StockMovement(
                    type="OUT", item_type="PRODUCT", item_id=oi.recipe_id,
                    quantity=oi.quantity,
                    description=f"Venda Pedido #{order.id}",
                ))

    db.commit()
    return JSONResponse({"id": order.id, "status": order.status})


@app.delete("/orders/{order_id}")
async def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.SalesOrder).filter_by(id=order_id).first()
    if order:
        db.delete(order)
        db.commit()
    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
