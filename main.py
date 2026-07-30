import json
import os
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Optional
from datetime import datetime, timedelta
import bcrypt as _bcrypt

import models
import label_service
from database import SessionLocal, engine

# ── Auth helpers ──────────────────────────────────────────────────────────────

_SECRET_KEY = os.environ.get("SECRET_KEY", "smartfood-ops-360-dev-key-mude-em-producao!!")

def hash_senha(senha: str) -> str:
    return _bcrypt.hashpw(senha.encode(), _bcrypt.gensalt()).decode()

def verificar_senha(senha: str, hash_str: str) -> bool:
    try:
        return _bcrypt.checkpw(senha.encode(), hash_str.encode())
    except Exception:
        return False


# ── Auth middleware ───────────────────────────────────────────────────────────

class AuthMiddleware(BaseHTTPMiddleware):
    _PUBLIC = {"/login", "/logout"}
    _PUBLIC_PREFIX = ("/produto/", "/qr/")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self._PUBLIC or any(path.startswith(p) for p in self._PUBLIC_PREFIX):
            return await call_next(request)

        user_id = request.session.get("user_id")
        if not user_id:
            if request.headers.get("HX-Request"):
                return Response(headers={"HX-Redirect": "/login"}, status_code=200)
            return RedirectResponse("/login", status_code=302)

        tipo = request.session.get("tipo_usuario", "")

        # /admin/usuarios — ADMIN only
        if path.startswith("/admin/usuarios") and tipo != "ADMIN":
            return HTMLResponse("Acesso negado.", status_code=403)

        # CLIENTE só pode acessar /loja/*
        if tipo == "CLIENTE" and not path.startswith("/loja"):
            if request.headers.get("HX-Request"):
                return Response(headers={"HX-Redirect": "/loja"}, status_code=200)
            return RedirectResponse("/loja", status_code=302)

        return await call_next(request)

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
    # Descontos em pedidos
    "ALTER TABLE sales_orders ADD COLUMN discount_amount REAL DEFAULT 0.0",

    # v3.0 Etapa B — Portal do Cliente B2B
    "ALTER TABLE recipes ADD COLUMN nome_comercial TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN foto_url TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN descricao_venda TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN unidade_venda TEXT DEFAULT 'pacote'",
    "ALTER TABLE recipes ADD COLUMN visivel_loja INTEGER DEFAULT 0",

    # v3.0 Etapa C — Guia QR
    "ALTER TABLE recipes ADD COLUMN fotos_apresentacao TEXT DEFAULT '[]'",
    "ALTER TABLE recipes ADD COLUMN dicas_apresentacao TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN nomes_cardapio TEXT DEFAULT '[]'",
    "ALTER TABLE recipes ADD COLUMN alertas_preparo TEXT DEFAULT ''",
]
with engine.connect() as _conn:
    for _sql in _MIGRATIONS:
        try:
            _conn.execute(text(_sql))
            _conn.commit()
        except Exception:
            pass  # column already exists

app = FastAPI(title="SmartFood Ops 360")

# Middleware order: AuthMiddleware added first (inner), SessionMiddleware added second (outer).
# Execution order: SessionMiddleware → AuthMiddleware → route handler.
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=_SECRET_KEY,
    max_age=86400,
    same_site="lax",
    https_only=False,
)

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
templates.env.filters["from_json"] = lambda s: json.loads(s) if s else []

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Etapa A: Autenticação ─────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, erro: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "erro": erro})


@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter_by(email=email.strip().lower(), ativo=1).first()
    if not user or not verificar_senha(senha, user.senha_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "erro": "E-mail ou senha incorretos."},
            status_code=200,
        )
    user.ultimo_acesso = datetime.utcnow()
    db.commit()

    request.session["user_id"] = user.id
    request.session["user_nome"] = user.nome
    request.session["tipo_usuario"] = user.tipo_usuario
    if user.cliente_id:
        request.session["cliente_id"] = user.cliente_id

    dest = "/loja" if user.tipo_usuario == "CLIENTE" else "/dashboard"
    return RedirectResponse(dest, status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ── Etapa A: Gestão de Usuários (ADMIN) ──────────────────────────────────────

@app.get("/admin/usuarios", response_class=HTMLResponse)
async def admin_usuarios(request: Request, db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.nome).all()
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    return templates.TemplateResponse("admin/usuarios.html", {
        "request": request,
        "active_page": "admin_usuarios",
        "users": users,
        "customers": customers,
        "current_user_id": request.session.get("user_id"),
    })


@app.post("/admin/usuarios", response_class=HTMLResponse)
async def admin_criar_usuario(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    tipo_usuario: str = Form(...),
    cliente_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if len(senha) < 8:
        return HTMLResponse(
            '<div class="alert-error">Senha mínima: 8 caracteres.</div>', status_code=422
        )
    if tipo_usuario == "CLIENTE" and not cliente_id:
        return HTMLResponse(
            '<div class="alert-error">Selecione o cliente vinculado.</div>', status_code=422
        )
    if db.query(models.User).filter_by(email=email).first():
        return HTMLResponse(
            '<div class="alert-error">E-mail já cadastrado.</div>', status_code=422
        )
    user = models.User(
        nome=nome,
        email=email,
        senha_hash=hash_senha(senha),
        tipo_usuario=tipo_usuario,
        cliente_id=cliente_id if tipo_usuario == "CLIENTE" else None,
    )
    db.add(user)
    db.commit()
    return HTMLResponse(
        '<div class="alert-success">Usuário criado com sucesso!</div>'
        '<script>setTimeout(()=>location.reload(),800)</script>',
    )


@app.put("/admin/usuarios/{user_id}", response_class=HTMLResponse)
async def admin_editar_usuario(
    user_id: int,
    nome: str = Form(...),
    email: str = Form(...),
    tipo_usuario: str = Form(...),
    cliente_id: Optional[int] = Form(None),
    ativo: int = Form(1),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404)
    email = email.strip().lower()
    conflict = db.query(models.User).filter(
        models.User.email == email, models.User.id != user_id
    ).first()
    if conflict:
        return HTMLResponse('<div class="alert-error">E-mail já em uso.</div>', status_code=422)
    user.nome = nome
    user.email = email
    user.tipo_usuario = tipo_usuario
    user.cliente_id = cliente_id if tipo_usuario == "CLIENTE" else None
    user.ativo = ativo
    db.commit()
    return HTMLResponse(
        '<div class="alert-success">Salvo!</div>'
        '<script>setTimeout(()=>location.reload(),600)</script>',
    )


@app.post("/admin/usuarios/{user_id}/reset-senha", response_class=HTMLResponse)
async def admin_reset_senha(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404)
    import secrets, string
    nova = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    user.senha_hash = hash_senha(nova)
    db.commit()
    return HTMLResponse(
        f'<div class="alert-success">'
        f'Nova senha gerada: <code class="font-mono font-bold">{nova}</code>'
        f'<br><small>Copie e envie ao usuário. Não será exibida novamente.</small></div>'
    )


@app.delete("/admin/usuarios/{user_id}", response_class=HTMLResponse)
async def admin_desativar_usuario(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    if user_id == request.session.get("user_id"):
        return HTMLResponse('<div class="alert-error">Você não pode desativar ou remover sua própria conta.</div>', status_code=422)
    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(404)
    
    if user.ativo == 0:
        db.delete(user)
        db.commit()
        return HTMLResponse(
            '<div class="alert-success">Usuário removido permanentemente.</div>'
            '<script>setTimeout(()=>location.reload(),600)</script>',
        )
    else:
        user.ativo = 0
        db.commit()
        return HTMLResponse(
            '<div class="alert-success">Usuário desativado.</div>'
            '<script>setTimeout(()=>location.reload(),600)</script>',
        )



@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/cadastros", response_class=HTMLResponse)
async def cadastros_page(request: Request, db: Session = Depends(get_db)):
    ingredients = db.query(models.Ingredient).order_by(models.Ingredient.name).all()
    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()
    manufacturers = db.query(models.IngredientManufacturer).order_by(models.IngredientManufacturer.brand_name).all()
    catalog = db.query(models.SupplierCatalog).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "active_page": "cadastros",
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
        "active_page": "ficha",
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
    return HTMLResponse(content=_ing_row(ing), status_code=201)


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
    manufacturer_id: str = Form(None),
    last_price: float = Form(...),
    db: Session = Depends(get_db)
):
    man_id = int(manufacturer_id) if manufacturer_id and manufacturer_id.strip() else None
    new_entry = models.SupplierCatalog(
        supplier_id=supplier_id,
        ingredient_id=ingredient_id,
        manufacturer_id=man_id,
        last_price=last_price
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)
    
    return HTMLResponse(content=(
        f'<tr id="cat-{new_entry.id}" class="hover:bg-gray-800/40" data-sid="{new_entry.supplier_id}">'
        f'<td class="py-2 px-2 text-gray-300">{new_entry.supplier.name}</td>'
        f'<td class="py-2 px-2 text-gray-300">{new_entry.ingredient.name}</td>'
        f'<td class="py-2 px-2 text-gray-400">{new_entry.manufacturer.brand_name if new_entry.manufacturer else "Sem marca"}</td>'
        f'<td class="py-2 px-2 text-right font-medium text-blue-300">R$ {new_entry.last_price:.2f}</td>'
        f'<td class="py-2 px-2 text-right">'
        f'<a href="/precos" class="text-xs text-gray-500 hover:text-blue-400">✏️</a>'
        f'<button hx-delete="/catalog/{new_entry.id}"'
        f' hx-target="#cat-{new_entry.id}" hx-swap="outerHTML"'
        f' hx-confirm="Remover esta entrada do catálogo?"'
        f' class="icon-btn hover:text-red-400 ml-1">🗑️</button>'
        f'</td>'
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
        return HTMLResponse(content='<option value="">Sem marca (Genérico)</option>')
    return HTMLResponse(content='<option value="">Sem marca (Genérico)</option>' + options)


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

    shopping_lists = (
        db.query(models.ShoppingList)
        .order_by(models.ShoppingList.id.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("precos.html", {
        "request": request,
        "active_page": "cotacoes",
        "groups": groups,
        "suppliers": suppliers,
        "ingredients": ingredients,
        "shopping_lists": shopping_lists,
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

    # KPI: ingredients with zero stock
    kpi_critical = (db.query(models.Ingredient)
                    .filter(models.Ingredient.current_stock <= 0).count())

    # Recent batches for the dashboard widget
    recent_batches = (db.query(models.ProductionBatch)
                      .order_by(models.ProductionBatch.production_date.desc())
                      .limit(5).all())

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active_page": "dashboard",
        "limite": limite,
        "below_limit": below,
        "ok_list": ok_list,
        "total": len(all_metrics),
        "kpi_recipes_at_risk": len(below),
        "kpi_critical_ingredients": kpi_critical,
        "recent_batches": recent_batches,
    })


@app.get("/api/search")
async def api_search(q: str = "", db: Session = Depends(get_db)):
    """Global Ctrl+K search — returns recipes + ingredients matching query."""
    if not q or len(q) < 2:
        return []
    pattern = f"%{q}%"
    results = []

    recipes = (db.query(models.Recipe)
               .filter(models.Recipe.name.ilike(pattern))
               .limit(5).all())
    for r in recipes:
        results.append({
            "type": "Ficha Técnica",
            "name": r.name,
            "url": f"/ficha-tecnica",
            "icon": "📋",
        })

    ingredients = (db.query(models.Ingredient)
                   .filter(models.Ingredient.name.ilike(pattern))
                   .limit(4).all())
    for i in ingredients:
        results.append({
            "type": "Insumo",
            "name": f"{i.name} ({i.unit})",
            "url": "/cadastros",
            "icon": "📦",
        })

    return results

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
            f"<a href='/cadastros' class='text-blue-400 underline'>Cadastros</a>.</p>"
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
        "active_page": "compras",
        "recipes": recipes,
    })


@app.post("/api/save-production-plan", response_class=HTMLResponse)
async def save_production_plan(request: Request, db: Session = Depends(get_db)):
    """Formaliza o planejamento de produção criando lotes pendentes para a Cozinha."""
    plan = await request.json()
    criados = 0
    for item in plan:
        recipe = db.query(models.Recipe).filter_by(id=item.get("recipe_id")).first()
        if recipe:
            batch = models.ProductionBatch(
                batch_number=f"PLAN-{datetime.utcnow().strftime('%y%m%d%H%M')}-{recipe.id}",
                product_name=recipe.name,
                recipe_id=recipe.id,
                expiry_date=datetime.utcnow() + timedelta(days=90),
                weight_kg=0.0,
            )
            db.add(batch)
            criados += 1
    db.commit()
    return HTMLResponse(
        f'<div class="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold"'
        f'     style="background:#f0fdf4;border:1px solid #bbf7d0;color:#15803d">'
        f'  <span class="text-lg">✅</span>'
        f'  {criados} ordem{"ns" if criados != 1 else ""} de produção enviada{"s" if criados != 1 else ""} '
        f'  para a <a href="/producao" style="text-decoration:underline;font-weight:700">Cozinha</a>!'
        f'</div>'
    )


@app.post("/api/shopping-list")
async def generate_shopping_list(request: Request, db: Session = Depends(get_db)):
    """Gera cotação RFQ: um card por fornecedor compatível com checkboxes por item."""
    body = await request.json()
    agg: dict[int, dict] = {}

    # 1. Agrega ingredientes respeitando o rendimento base da receita
    for entry in body:
        recipe_id = int(entry.get("recipe_id", 0))
        portions  = float(entry.get("portions", 1) or 1)
        recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
        if not recipe:
            continue

        base_portions = recipe.rendimento_unidades if recipe.rendimento_unidades else 1
        multiplier = portions / base_portions

        for section in recipe.sections:
            for item in section.items:
                ing = item.ingredient
                if not ing:
                    continue
                qty_bruto = item.quantity * item.correction_factor * multiplier
                if ing.id not in agg:
                    agg[ing.id] = {
                        "name": ing.name, "unit": ing.unit, "qty": 0.0,
                        "category": ing.category or "Outros",
                        "alternatives": [],
                    }
                agg[ing.id]["qty"] += qty_bruto

    if not agg:
        return HTMLResponse(
            '<p class="text-sm py-8 text-center" style="color:var(--muted)">'
            'Nenhum insumo encontrado nas receitas selecionadas.</p>'
        )

    # 2. Mapeia TODOS os fornecedores elegíveis: via catálogo OU via categoria
    all_suppliers = db.query(models.Supplier).all()

    for ing_id, data in agg.items():
        catalog_entries = db.query(models.SupplierCatalog).filter_by(ingredient_id=ing_id).all()
        cat_prices = {c.supplier_id: c.last_price or 0.0 for c in catalog_entries}

        for sup in all_suppliers:
            sup_cats = [sc.category for sc in sup.supplier_categories]
            if sup.id in cat_prices or data["category"] in sup_cats:
                data["alternatives"].append({
                    "supplier_id":    str(sup.id),
                    "supplier_name":  sup.name,
                    "supplier_phone": sup.contact_info or "",
                    "price":          cat_prices.get(sup.id, 0.0),
                })

    # 3. Monta grupos por fornecedor (card por fornecedor)
    groups: dict[str, dict] = {}
    for data in agg.values():
        if not data["alternatives"]:
            if "0" not in groups:
                groups["0"] = {"name": "Sem Fornecedor Compatível", "phone": "", "items": []}
            groups["0"]["items"].append({
                "name": data["name"], "qty": data["qty"],
                "unit": data["unit"], "price": 0.0, "selected": True,
            })
        else:
            for alt in data["alternatives"]:
                sid = alt["supplier_id"]
                if sid not in groups:
                    groups[sid] = {
                        "name":  alt["supplier_name"],
                        "phone": alt["supplier_phone"],
                        "items": [],
                    }
                groups[sid]["items"].append({
                    "name":     data["name"],
                    "qty":      data["qty"],
                    "unit":     data["unit"],
                    "price":    alt["price"],
                    "selected": True,
                })

    # 4. Salva no banco para cruzamento com /precos
    save_banner = ""
    save_ok = False
    try:
        s_list = models.ShoppingList(
            name=f"Cotação gerada em {datetime.utcnow().strftime('%d/%m/%Y às %H:%M')}"
        )
        db.add(s_list)
        db.flush()
        for ing_id, data in agg.items():
            db.add(models.ShoppingListItem(
                list_id=s_list.id, ingredient_id=ing_id, qty=data["qty"]
            ))
        db.commit()
        save_banner = (
            '✓ Cotação salva — disponível em '
            '<a href="/precos" class="underline font-medium">Cotações</a>.'
        )
        save_ok = True
    except Exception as exc:
        db.rollback()
        save_banner = f'⚠ Cotação gerada mas não salva: {exc}'

    return templates.TemplateResponse("fragments/shopping_list_interactive.html", {
        "request":     request,
        "groups":      groups,
        "total_items": len(agg),
        "save_banner": save_banner,
        "save_ok":     save_ok,
    })


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
        "active_page": "etiquetas",
        "label_templates": label_templates,
        "batches": batches,
        "recipes": recipes,
        "templates_json": templates_json,
        "batches_json": batches_json,
        "recipes_ingredients": recipes_ingredients,
    })


def _validate_label_dims(width_mm: float, height_mm: float) -> None:
    """Sanity bounds covering common thermal label printers (2"-8.6" wide rolls) —
    catches data-entry mistakes (e.g. cm typed instead of mm) before they reach
    the printer, without hard-coding one specific printer model's max width."""
    if not (10 <= width_mm <= 220):
        raise HTTPException(422, detail="Largura da etiqueta deve estar entre 10mm e 220mm.")
    if not (5 <= height_mm <= 400):
        raise HTTPException(422, detail="Altura da etiqueta deve estar entre 5mm e 400mm.")


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
    _validate_label_dims(width_mm, height_mm)
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
    _validate_label_dims(width_mm, height_mm)
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
    elif tpl.printer_type == "PPLB":
        # PPLB embeds a binary QR raster inline — decode just for display,
        # replacing undisplayable bytes; the actual bytes sent are untouched.
        cmd = label_service.generate_pplb(template_data, print_data).decode("cp850", errors="replace")
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

    quantity = max(1, min(quantity, 5000))

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
        encoding = "cp1252"
    elif tpl.printer_type == "PPLB":
        cmd = label_service.generate_pplb(template_data, print_data, quantity)
        encoding = "cp850"  # unused for bytes, kept for consistency/clarity
    else:
        cmd = label_service.generate_zpl(template_data, print_data, quantity)
        encoding = "utf-8"

    if not tpl.printer_ip:
        return HTMLResponse(
            content='<div class="p-3 bg-yellow-500/20 text-yellow-300 rounded text-sm">⚠️ IP da impressora não configurado no template.</div>'
        )

    ok, msg = label_service.send_to_printer(tpl.printer_ip, tpl.printer_port, cmd, encoding=encoding)
    css = "green" if ok else "red"
    icon = "✅" if ok else "❌"
    return HTMLResponse(
        content=f'<div class="p-3 bg-{css}-500/20 text-{css}-300 rounded text-sm">{icon} {msg}</div>'
    )


@app.get("/labels/teste-impressora", response_class=HTMLResponse)
async def teste_impressora(ip: str = "192.168.15.90", port: int = 9100):
    """Envia um print de teste para verificar se a impressora está acessível."""
    ok, msg = label_service.enviar_teste_impressora(ip, port)
    icon  = "✅" if ok else "❌"
    ping_html = (
        f'<div style="padding:.85rem 1rem;border-radius:.5rem;font-size:.85rem;'
        f'background:{"#f0fdf4" if ok else "#fef2f2"};'
        f'border:1px solid {"#bbf7d0" if ok else "#fecaca"};'
        f'color:{"#15803d" if ok else "#dc2626"}">'
        f'{icon} <strong>{ip}:{port}</strong> — {msg}</div>'
    )
    return HTMLResponse(content=ping_html)


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

    # Etapa C: auto-preenche tutorial_url com URL interna se não fornecida
    if not tutorial_url:
        batch.tutorial_url = f"/produto/{batch.id}"

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
        batch_id=batch.id,
    )
    return RedirectResponse(url=url, status_code=302)


# ── Módulo Produção (KDS — Kitchen Display System) ───────────────────────────

@app.get("/producao", response_class=HTMLResponse)
async def producao_page(request: Request, db: Session = Depends(get_db)):
    """Tela de execução da cozinha — escala porções e finaliza lotes."""
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()

    recipes_json = []
    for r in recipes:
        sections = []
        for sec in r.sections:
            items = []
            for it in sec.items:
                items.append({
                    "name":     it.ingredient.name if it.ingredient else "Insumo Removido",
                    "unit":     it.ingredient.unit if it.ingredient else "",
                    "base_qty": it.quantity,
                    "fc":       it.correction_factor,
                })
            sections.append({
                "name":       sec.name,
                "instrucoes": sec.instrucoes or "",
                "items":      items,
            })

        recipes_json.append({
            "id":              r.id,
            "name":            r.name,
            "rendimento_base": r.rendimento_unidades or 1,
            "sections":        sections,
        })

    # Lotes pendentes criados pelo planejamento de compras (PLAN-...)
    pending_batches = (
        db.query(models.ProductionBatch)
        .filter(models.ProductionBatch.batch_number.like("PLAN-%"))
        .filter(models.ProductionBatch.recipe_id.isnot(None))
        .order_by(models.ProductionBatch.production_date.desc())
        .limit(10)
        .all()
    )

    return templates.TemplateResponse("producao.html", {
        "request":         request,
        "active_page":     "producao",
        "recipes_json":    recipes_json,
        "pending_batches": pending_batches,
    })


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
    discount_amount = max(0.0, float(body.get("discount_amount", 0)))

    if not customer_id:
        raise HTTPException(422, "Cliente obrigatório")
    if not items:
        raise HTTPException(422, "Adicione ao menos um produto")

    customer = db.query(models.Customer).filter_by(id=customer_id).first()
    if not customer:
        raise HTTPException(404, "Cliente não encontrado")

    subtotal = 0.0
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
        subtotal += qty * unit_price

    discount_amount = min(discount_amount, subtotal)
    order.discount_amount = round(discount_amount, 2)
    order.total_amount = round(max(0.0, subtotal - discount_amount), 2)
    db.commit()
    db.refresh(order)
    _invalidar_cache()
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


# ── Etapa B: Portal do Cliente B2B ───────────────────────────────────────────

def _preco_para_cliente(recipe: models.Recipe, customer_id: int, db: Session) -> float:
    pt = db.query(models.PriceTable).filter_by(
        customer_id=customer_id, recipe_id=recipe.id
    ).first()
    if pt:
        return pt.preco
    return _recipe_sale_price(recipe, db)


@app.get("/loja", response_class=HTMLResponse)
async def loja_catalogo(request: Request, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    customer = db.query(models.Customer).filter_by(id=cliente_id).first() if cliente_id else None
    recipes = db.query(models.Recipe).filter_by(visivel_loja=1).order_by(models.Recipe.nome_comercial).all()
    config = db.query(models.CompanyConfig).first()
    produtos = []
    for r in recipes:
        nome = r.nome_comercial or r.name
        preco = _preco_para_cliente(r, cliente_id, db) if cliente_id else _recipe_sale_price(r, db)
        produtos.append({
            "id": r.id,
            "nome": nome,
            "foto_url": r.foto_url or "",
            "descricao": r.descricao_venda or "",
            "unidade_venda": r.unidade_venda or "pacote",
            "rendimento": r.rendimento_unidades or 1,
            "preco": round(preco, 2),
            "stock": r.current_stock_units or 0,
        })
    return templates.TemplateResponse("loja/catalogo.html", {
        "request": request,
        "customer": customer,
        "produtos": produtos,
        "config": config,
        "user_nome": request.session.get("user_nome", ""),
    })


@app.get("/loja/carrinho", response_class=HTMLResponse)
async def loja_carrinho(request: Request, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    customer = db.query(models.Customer).filter_by(id=cliente_id).first() if cliente_id else None
    config = db.query(models.CompanyConfig).first()
    return templates.TemplateResponse("loja/carrinho.html", {
        "request": request,
        "customer": customer,
        "config": config,
        "user_nome": request.session.get("user_nome", ""),
    })


@app.get("/loja/pedidos", response_class=HTMLResponse)
async def loja_pedidos(request: Request, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return RedirectResponse("/loja", status_code=302)
    customer = db.query(models.Customer).filter_by(id=cliente_id).first()
    orders = (
        db.query(models.SalesOrder)
        .filter_by(customer_id=cliente_id)
        .order_by(models.SalesOrder.order_date.desc())
        .limit(50).all()
    )
    return templates.TemplateResponse("loja/pedidos.html", {
        "request": request,
        "customer": customer,
        "orders": orders,
        "user_nome": request.session.get("user_nome", ""),
    })


@app.get("/loja/pedidos/{order_id}", response_class=HTMLResponse)
async def loja_pedido_detalhe(request: Request, order_id: int, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    order = db.query(models.SalesOrder).filter_by(id=order_id, customer_id=cliente_id).first()
    if not order:
        raise HTTPException(404)
    return templates.TemplateResponse("loja/pedidos.html", {
        "request": request,
        "order_detalhe": order,
        "user_nome": request.session.get("user_nome", ""),
    })


@app.post("/loja/orders")
async def loja_criar_pedido(request: Request, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        raise HTTPException(403)
    body = await request.json()
    items = body.get("items", [])
    notes = body.get("notes", "")
    if not items:
        raise HTTPException(422, "Carrinho vazio")
    subtotal = 0.0
    order = models.SalesOrder(customer_id=cliente_id, status="PENDING", notes=notes)
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
            order_id=order.id, recipe_id=recipe_id, quantity=qty, unit_price=unit_price
        ))
        subtotal += qty * unit_price
    order.total_amount = round(subtotal, 2)
    db.commit()
    db.refresh(order)
    return JSONResponse({"id": order.id, "total": order.total_amount})


# ── Etapa B: Painel Admin — Catálogo da Loja ─────────────────────────────────

@app.get("/admin/loja", response_class=HTMLResponse)
async def admin_loja(request: Request, db: Session = Depends(get_db)):
    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    config = db.query(models.CompanyConfig).first()
    price_tables = db.query(models.PriceTable).all()
    pt_map = {(pt.customer_id, pt.recipe_id): pt.preco for pt in price_tables}
    return templates.TemplateResponse("admin/loja.html", {
        "request": request,
        "active_page": "admin_loja",
        "recipes": recipes,
        "customers": customers,
        "config": config,
        "pt_map": pt_map,
    })


@app.post("/admin/loja/produto/{recipe_id}", response_class=HTMLResponse)
async def admin_loja_produto(
    recipe_id: int,
    nome_comercial: str = Form(""),
    descricao_venda: str = Form(""),
    foto_url: str = Form(""),
    visivel_loja: int = Form(0),
    unidade_venda: str = Form("pacote"),
    alertas_preparo: str = Form(""),
    dicas_apresentacao: str = Form(""),
    nomes_cardapio_raw: str = Form(""),
    fotos_apresentacao_raw: str = Form(""),
    db: Session = Depends(get_db),
):
    recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        raise HTTPException(404)
    recipe.nome_comercial = nome_comercial
    recipe.descricao_venda = descricao_venda
    recipe.foto_url = foto_url
    recipe.visivel_loja = visivel_loja
    recipe.unidade_venda = unidade_venda or "pacote"
    recipe.alertas_preparo = alertas_preparo
    recipe.dicas_apresentacao = dicas_apresentacao
    nomes = [n.strip() for n in nomes_cardapio_raw.splitlines() if n.strip()]
    recipe.nomes_cardapio = json.dumps(nomes, ensure_ascii=False)
    fotos = [f.strip() for f in fotos_apresentacao_raw.splitlines() if f.strip()]
    recipe.fotos_apresentacao = json.dumps(fotos, ensure_ascii=False)
    db.commit()
    return HTMLResponse(
        '<div class="alert-success">Produto atualizado!</div>',
        headers={"HX-Trigger": '{"showToast":{"msg":"Produto atualizado","type":"success"}}'},
    )


@app.post("/admin/loja/preco", response_class=HTMLResponse)
async def admin_loja_preco(
    customer_id: int = Form(...),
    recipe_id: int = Form(...),
    preco: float = Form(...),
    db: Session = Depends(get_db),
):
    pt = db.query(models.PriceTable).filter_by(
        customer_id=customer_id, recipe_id=recipe_id
    ).first()
    if pt:
        pt.preco = preco
    else:
        db.add(models.PriceTable(customer_id=customer_id, recipe_id=recipe_id, preco=preco))
    db.commit()
    return HTMLResponse(
        '<div class="alert-success">Preço salvo!</div>',
        headers={"HX-Trigger": '{"showToast":{"msg":"Preço atualizado","type":"success"}}'},
    )


@app.post("/admin/loja/config", response_class=HTMLResponse)
async def admin_loja_config(
    whatsapp_contato: str = Form(""),
    nome_fantasia: str = Form("SmartFood"),
    logo_url: str = Form(""),
    db: Session = Depends(get_db),
):
    config = db.query(models.CompanyConfig).first()
    if config:
        config.whatsapp_contato = whatsapp_contato
        config.nome_fantasia = nome_fantasia
        config.logo_url = logo_url
    else:
        db.add(models.CompanyConfig(
            whatsapp_contato=whatsapp_contato,
            nome_fantasia=nome_fantasia,
            logo_url=logo_url,
        ))
    db.commit()
    return HTMLResponse(
        '<div class="alert-success">Configurações salvas!</div>',
        headers={"HX-Trigger": '{"showToast":{"msg":"Configurações salvas","type":"success"}}'},
    )


# ── Etapa C: Guia do Produto via QR Code (rota pública) ──────────────────────

@app.get("/produto/{batch_id}", response_class=HTMLResponse)
async def produto_guia(request: Request, batch_id: int, db: Session = Depends(get_db)):
    batch = db.query(models.ProductionBatch).filter_by(id=batch_id).first()
    if not batch:
        return templates.TemplateResponse("public/produto_404.html", {"request": request}, status_code=404)

    recipe = db.query(models.Recipe).filter_by(id=batch.recipe_id).first() if batch.recipe_id else None
    config = db.query(models.CompanyConfig).first()

    # Frescor badge
    now = datetime.utcnow()
    dias_restantes = (batch.expiry_date - now).days
    if dias_restantes >= 7:
        frescor_classe = "green"
    elif dias_restantes >= 1:
        frescor_classe = "yellow"
    else:
        frescor_classe = "red"

    nome_produto = (recipe.nome_comercial if recipe and recipe.nome_comercial else None) or batch.product_name
    fotos_ap = json.loads(recipe.fotos_apresentacao or "[]") if recipe else []
    nomes_cardapio = json.loads(recipe.nomes_cardapio or "[]") if recipe else []

    return templates.TemplateResponse("public/produto.html", {
        "request": request,
        "batch": batch,
        "recipe": recipe,
        "config": config,
        "nome_produto": nome_produto,
        "dias_restantes": dias_restantes,
        "frescor_classe": frescor_classe,
        "fotos_apresentacao": fotos_ap,
        "nomes_cardapio": nomes_cardapio,
    })


# ── v4.0 Inteligência — Cache simples (5 min TTL) ────────────────────────────

import time as _time
_intelligence_cache: dict = {}
_CACHE_TTL = 300


def _invalidar_cache():
    _intelligence_cache.clear()


def _get_plano_cached(db: Session) -> list[dict]:
    import intelligence_engine as ie
    agora = _time.time()
    if "plano" in _intelligence_cache:
        dados, ts = _intelligence_cache["plano"]
        if agora - ts < _CACHE_TTL:
            return dados
    plano = ie.gerar_plano_producao_semanal(db)
    _intelligence_cache["plano"] = (plano, agora)
    return plano


# ── Etapa D: Painel de Inteligência de Produção ───────────────────────────────

@app.get("/inteligencia", response_class=HTMLResponse)
async def inteligencia_page(request: Request, db: Session = Depends(get_db)):
    import intelligence_engine as ie
    plano = _get_plano_cached(db)

    criticos  = [p for p in plano if p["urgencia"] == "CRITICO"]
    alertas   = [p for p in plano if p["urgencia"] == "ALERTA"]
    planejar  = [p for p in plano if p["urgencia"] == "PLANEJAR"]
    ok        = [p for p in plano if p["urgencia"] == "OK"]
    excesso   = [p for p in plano if p["urgencia"] == "EXCESSO"]
    sem_dem   = [p for p in plano if p["urgencia"] == "SEM_DEMANDA"]

    # KPI: valor estimado de demanda semanal
    demanda_semana_rs = sum(
        p["media_semanal"] * _recipe_sale_price(
            db.query(models.Recipe).filter_by(id=p["recipe_id"]).first(), db
        )
        for p in plano if p.get("media_semanal", 0) > 0
        and db.query(models.Recipe).filter_by(id=p["recipe_id"]).first()
    )

    # Tendência geral: média ponderada dos crescimentos
    vals = [p["crescimento_pct"] for p in plano if p.get("media_semanal", 0) > 0]
    crescimento_geral = round(sum(vals) / len(vals), 1) if vals else 0.0

    recipes = db.query(models.Recipe).order_by(models.Recipe.name).all()
    return templates.TemplateResponse("inteligencia.html", {
        "request": request,
        "active_page": "inteligencia",
        "criticos": criticos,
        "alertas": alertas,
        "planejar": planejar,
        "ok": ok,
        "excesso": excesso,
        "sem_demanda": sem_dem,
        "total_criticos": len(criticos),
        "total_alertas": len(alertas),
        "demanda_semana_rs": round(demanda_semana_rs, 2),
        "crescimento_geral": crescimento_geral,
        "recipes": recipes,
        "atualizado_em": datetime.utcnow(),
    })


@app.get("/api/inteligencia/grafico/{recipe_id}", response_class=HTMLResponse)
async def inteligencia_grafico(
    recipe_id: int,
    janela: int = 12,
    db: Session = Depends(get_db),
):
    import intelligence_engine as ie
    serie = ie.serie_historica_cliente(
        customer_id=None,
        db=db,
        recipe_id=recipe_id,
        granularidade="semana",
        janela_semanas=janela,
    )
    svg = ie.gerar_grafico_svg(serie)
    recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
    media = round(sum(s["quantidade"] for s in serie) / max(len(serie), 1), 1)
    pico  = max((s["quantidade"] for s in serie), default=0)
    minimo = min((s["quantidade"] for s in serie), default=0)
    return HTMLResponse(f"""
        <div style="margin-bottom:.5rem">{svg}</div>
        <div style="display:flex;gap:1.5rem;font-size:.78rem;color:var(--sub);flex-wrap:wrap">
          <span>Média: <strong style="color:var(--text)">{media:.0f} un/sem</strong></span>
          <span>Pico: <strong style="color:var(--text)">{pico:.0f}</strong></span>
          <span>Mínimo: <strong style="color:var(--text)">{minimo:.0f}</strong></span>
        </div>
    """)


# ── Etapas E + F: Portal do Cliente ──────────────────────────────────────────

def _get_current_customer(request: Request, db: Session) -> models.Customer | None:
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return None
    return db.query(models.Customer).filter_by(id=cliente_id).first()


@app.get("/loja/consumo", response_class=HTMLResponse)
async def loja_consumo_page(request: Request, db: Session = Depends(get_db)):
    import intelligence_engine as ie
    customer = _get_current_customer(request, db)
    if not customer:
        return RedirectResponse("/loja", status_code=302)

    serie_mensal  = ie.serie_historica_cliente(customer.id, db, granularidade="mes",    janela_semanas=52)
    serie_semanal = ie.serie_historica_cliente(customer.id, db, granularidade="semana", janela_semanas=12)

    mes_atual_qtd    = serie_mensal[-1]["quantidade"]    if serie_mensal else 0
    mes_anterior_qtd = serie_mensal[-2]["quantidade"]    if len(serie_mensal) >= 2 else 0
    gasto_mes        = serie_mensal[-1]["valor_total"]   if serie_mensal else 0
    var_mensal       = round(
        ((mes_atual_qtd - mes_anterior_qtd) / mes_anterior_qtd * 100)
        if mes_anterior_qtd else 0, 1
    )

    produtos_raw     = ie.produtos_do_cliente(customer.id, db)
    total_qtd        = sum(p["quantidade_total"] for p in produtos_raw)
    produtos_detalhes = []
    for p in produtos_raw:
        cres = ie.calcular_taxa_crescimento(p["recipe_id"], db, customer.id)
        sug  = ie.calcular_sugestao_pedido_cliente(p["recipe_id"], customer.id, db)
        produtos_detalhes.append({
            **p,
            "participacao_pct": round(p["quantidade_total"] / total_qtd * 100) if total_qtd else 0,
            **cres,
            "sugestao": sug,
        })

    return templates.TemplateResponse("loja/consumo.html", {
        "request": request,
        "user_nome": request.session.get("user_nome", ""),
        "customer": customer,
        "mes_atual_qtd": mes_atual_qtd,
        "mes_anterior_qtd": mes_anterior_qtd,
        "variacao_mensal_pct": var_mensal,
        "gasto_mes": gasto_mes,
        "serie_semanal": serie_semanal,
        "serie_mensal": serie_mensal,
        "produtos": produtos_detalhes,
    })


@app.get("/api/loja/sugestoes")
async def api_loja_sugestoes(request: Request, db: Session = Depends(get_db)):
    import intelligence_engine as ie
    customer = _get_current_customer(request, db)
    if not customer:
        raise HTTPException(403)
    recipes = db.query(models.Recipe).filter_by(visivel_loja=1).all()
    sugestoes = {}
    for recipe in recipes:
        sug = ie.calcular_sugestao_pedido_cliente(recipe.id, customer.id, db)
        sugestoes[str(recipe.id)] = sug
    return JSONResponse(sugestoes)


@app.get("/api/loja/alertas")
async def api_loja_alertas(request: Request, db: Session = Depends(get_db)):
    import intelligence_engine as ie
    customer = _get_current_customer(request, db)
    if not customer:
        raise HTTPException(403)
    produtos = ie.produtos_do_cliente(customer.id, db)
    alertas = []
    for p in produtos:
        sug = ie.calcular_sugestao_pedido_cliente(p["recipe_id"], customer.id, db)
        media_sem = sug.get("media_semanal_pacotes", 0)
        dias = p["dias_desde_ultimo"]
        if media_sem > 0 and dias > 10 and dias > (7 / max(media_sem, 0.1)):
            recipe = db.query(models.Recipe).filter_by(id=p["recipe_id"]).first()
            if recipe and recipe.visivel_loja:
                alertas.append({
                    "recipe_id": p["recipe_id"],
                    "recipe_name": p["recipe_name"],
                    "dias_desde_ultimo": dias,
                    "sugestao_pacotes": sug["sugestao_pacotes"],
                    "media_semanal": media_sem,
                })
    # Retorna apenas o mais urgente (maior dias/media ratio)
    alertas.sort(key=lambda x: x["dias_desde_ultimo"] / max(x["media_semanal"], 0.01), reverse=True)
    return JSONResponse(alertas[:1])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
