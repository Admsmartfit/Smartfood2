# PRD — Operação Integrada: Compras Inteligentes e Módulo de Cozinha
**Sistema:** SmartFood Ops 360 — v2.0  
**Data:** 28/04/2026  
**Princípio:** Cada etapa é autônoma, não quebra o que existe e pode ser revertida isoladamente.

---

## 1. Diagnóstico do Estado Atual

O sistema já possui uma base sólida e funcional:

- ✅ Cadastro de Insumos, Marcas e Fornecedores com catálogo de preços
- ✅ Ficha Técnica completa com BOM (Bill of Materials), FC, FCoc e margem de lucro
- ✅ Dashboard de margens com alertas e semáforo visual
- ✅ Lista de Compras (`/compras`) agrupada por categoria de ingrediente
- ✅ Módulo de Etiquetas e QR Code dinâmico
- ✅ Controle de Estoque (insumos e produtos)
- ✅ Módulo de Clientes e Pedidos de Venda

**Gaps identificados pela auditoria:**

| Gap | Módulo afetado | Impacto | Complexidade |
|---|---|---|---|
| Lista de compras agrupada por **categoria** (inútil para o comprador) | `/compras` | Alto | Médio |
| Sem botão de pedido via WhatsApp para o fornecedor | `/compras` | Alto | Baixo |
| Custo estimado do pedido não aparece na lista | `/compras` | Médio | Baixo |
| Itens sem fornecedor vinculado ficam invisíveis para cotação | `/compras` | Médio | Baixo |
| Cozinheira não tem tela própria de execução | Novo módulo | Alto | Médio |
| Escalar porções exige matemática manual | Novo módulo | Alto | Baixo |
| Concluir produção não gera Lote automaticamente | Novo módulo | Médio | Baixo |

---

## 2. Objetivos e Métricas de Sucesso

| Objetivo | Métrica | Meta |
|---|---|---|
| Reduzir tempo de montagem do pedido de compras | Minutos entre "gerar lista" e "enviar pedido" | < 2 min |
| Eliminar erros de proporção na cozinha | Ocorrências de retrabalho por cálculo errado | Zero |
| Aumentar rastreabilidade de lotes | % de produções com Lote gerado automaticamente | 100% |
| Adoção do módulo de cozinha | Acessos diários a `/producao` | ≥ 1 por dia de produção |

---

## 3. Escopo da Versão 2.0

Esta versão entrega **duas melhorias independentes** que podem ser implantadas em qualquer ordem.

```
Etapa A — Procurement Inteligente  →  compras.html + main.py
Etapa B — Módulo de Produção       →  producao.html + main.py (nova rota)
```

Não há alterações em modelos de banco de dados. Não há migrations necessárias. Ambas as etapas reutilizam dados já existentes em `SupplierCatalog`, `Recipe` e `ProductionBatch`.

---

## 4. Etapa A — Procurement Inteligente (`/compras`)

### 4.1 Problema detalhado

A tela atual agrupa os itens da lista de compras por **categoria culinária** (Carnes, Vegetais…). Essa visão é útil para organizar a despensa, mas inútil para o comprador, que precisa saber:

> *"Quais itens vou pedir para a Distribuidora São Paulo? Quanto vou gastar? Como envio o pedido?"*

Sistemas de mercado como **MarketMan** e **Kuker** resolvem isso agrupando a lista por **Fornecedor**, com valor estimado e ação direta de pedido.

### 4.2 Solução

Substituir o endpoint `POST /api/shopping-list` por uma nova versão que:

1. Mantém toda a lógica de agregação de ingredientes (sem regressão).
2. Cruza cada ingrediente com `SupplierCatalog` e identifica o fornecedor com o menor preço registrado (ou o último fornecedor usado).
3. Agrupa o resultado em **Cards de Fornecedor**.
4. Para cada fornecedor com telefone cadastrado, monta automaticamente uma mensagem de WhatsApp com a lista de itens e quantidades.
5. Itens sem fornecedor vinculado vão para um card especial **"Sem Fornecedor — Cotar"**, que não desaparece e serve de alerta visual.

### 4.3 Interface esperada

```
┌─────────────────────────────────────────────────┐
│  🏢 Distribuidora São Paulo          R$ 847,20  │
│  ─────────────────────────────────────────────  │
│  ☐  Peito de Frango     18,000 kg   R$ 340,20  │
│  ☐  Farinha de Trigo     5,500 kg   R$ 82,50   │
│  ☐  Requeijão            3,200 kg   R$ 96,00   │
│                                                 │
│  [ 📱 Enviar Pedido via WhatsApp ]              │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  ⚠️ Sem Fornecedor — Cotar                       │
│  ─────────────────────────────────────────────  │
│  ☐  Caldo de Galinha     0,450 kg               │
│  ☐  Pimenta do Reino     0,120 kg               │
│                                                 │
│  Cadastre o fornecedor em Insumos para pedir    │
│  via WhatsApp.                                  │
└─────────────────────────────────────────────────┘
```

### 4.4 Lógica do botão WhatsApp

A mensagem é montada no backend no momento da geração da lista. O link segue o padrão:

```
https://wa.me/{phone}?text={mensagem_urlencoded}
```

A mensagem contém:
- Saudação com o nome do fornecedor
- Lista de itens: `- {quantidade} {unidade} de {ingrediente}`
- Rodapé com pedido de confirmação

O número de telefone é lido de `supplier.contact_info`. Números com caracteres `( ) - espaço` são normalizados antes de compor o link.

### 4.5 Arquivos alterados

| Arquivo | Natureza da mudança |
|---|---|
| `main.py` | Substituição do `@app.post("/api/shopping-list")`. Adição de `import urllib.parse` no topo. |
| `templates/base.html` | Adição do link de `/producao` na sidebar (seção Fábrica). |

Nenhuma outra alteração é necessária. `compras.html` permanece **idêntico** — ele apenas consome o HTML retornado pelo endpoint.

### 4.6 Código — `main.py` (endpoint substituído)

```python
import urllib.parse  # adicionar no topo do arquivo, junto dos outros imports

@app.post("/api/shopping-list", response_class=HTMLResponse)
async def generate_shopping_list(request: Request, db: Session = Depends(get_db)):
    """Gera lista de compras agrupada por FORNECEDOR com custo estimado."""
    body = await request.json()
    agg: dict[int, dict] = {}

    # 1. Agrega ingredientes (mesma lógica anterior, mantém compatibilidade)
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
                        "supplier_name": "Sem Fornecedor Vinculado",
                        "supplier_phone": "", "estimated_price": 0.0
                    }
                agg[ing.id]["qty"] += qty_bruto

    if not agg:
        return HTMLResponse(
            '<p class="text-center text-gray-500 py-6">Nenhum insumo encontrado.</p>'
        )

    # 2. Descobre melhor/último fornecedor para cada ingrediente via SupplierCatalog
    grouped_by_supplier: dict[str, dict] = {}
    for ing_id, data in agg.items():
        cat = (
            db.query(models.SupplierCatalog)
            .filter_by(ingredient_id=ing_id)
            .order_by(models.SupplierCatalog.last_price.asc())
            .first()
        )
        if cat and cat.supplier:
            data["supplier_name"]  = cat.supplier.name
            data["supplier_phone"] = cat.supplier.contact_info or ""
            data["estimated_price"] = (cat.last_price or 0.0) * data["qty"]

        sup_name = data["supplier_name"]
        if sup_name not in grouped_by_supplier:
            grouped_by_supplier[sup_name] = {
                "phone": data["supplier_phone"], "items": [], "total": 0.0
            }
        grouped_by_supplier[sup_name]["items"].append(data)
        grouped_by_supplier[sup_name]["total"] += data["estimated_price"]

    # 3. Renderiza HTML com cards por fornecedor + botão WhatsApp
    html_parts = []
    for sup_name, sup_data in grouped_by_supplier.items():
        items_html = ""
        whatsapp_text = f"Olá {sup_name}! Gostaria de fazer o seguinte pedido:\n\n"

        for i in sup_data["items"]:
            items_html += f"""
            <li class="flex justify-between items-center py-2 border-b
                        border-gray-100 last:border-0 text-sm">
              <span>
                <input type="checkbox" class="mr-2 accent-blue-600">
                {i['name']}
              </span>
              <span class="font-semibold">
                {i['qty']:.3f} {i['unit']}
                <span class="text-xs text-gray-400 font-normal ml-2">
                  R$ {i['estimated_price']:.2f}
                </span>
              </span>
            </li>
            """
            whatsapp_text += f"- {i['qty']:.3f} {i['unit']} de {i['name']}\n"

        whatsapp_text += "\nAguardo confirmação. Obrigado!"

        # Normaliza o número: remove (  ) - espaços
        clean_phone = (
            sup_data["phone"]
            .replace(" ", "").replace("-", "")
            .replace("(", "").replace(")", "")
        )
        wa_link = (
            f"https://wa.me/{clean_phone}"
            f"?text={urllib.parse.quote(whatsapp_text)}"
        ) if clean_phone else "#"

        is_no_supplier = (sup_name == "Sem Fornecedor Vinculado")
        border_color   = "border-yellow-400" if is_no_supplier else "border-blue-500"
        cta_html = (
            '<p class="text-xs text-yellow-600 mt-3 p-2 bg-yellow-50 rounded-lg">'
            '⚠️ Cadastre o telefone do fornecedor em <a href="/" '
            'class="underline">Insumos</a> para pedir via WhatsApp.</p>'
            if is_no_supplier or not clean_phone
            else f'<a href="{wa_link}" target="_blank" '
                 f'class="mt-3 flex items-center justify-center gap-2 w-full py-2 '
                 f'bg-green-600 hover:bg-green-500 text-white text-sm '
                 f'font-semibold rounded-lg transition-colors">'
                 f'📱 Enviar Pedido via WhatsApp</a>'
        )

        html_parts.append(f"""
        <div class="card p-4 mb-4 border-l-4 {border_color}">
          <div class="flex justify-between items-start mb-3">
            <div>
              <h3 class="font-bold text-gray-800">{sup_name}</h3>
              <p class="text-xs text-gray-500">
                Valor Estimado: R$ {sup_data['total']:.2f}
              </p>
            </div>
          </div>
          <ul class="text-gray-700">{items_html}</ul>
          {cta_html}
        </div>
        """)

    # 4. Salva a lista no banco (mantido da versão anterior)
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
    except Exception:
        db.rollback()

    return HTMLResponse("".join(html_parts))
```

### 4.7 Código — `templates/base.html` (sidebar)

Substituir o bloco da seção **Fábrica** dentro da `<nav>`:

```html
<hr x-show="sidebarOpen" style="border:none;border-top:1px solid var(--border);margin:.5rem .75rem">
<p class="sidebar-section-label" x-show="sidebarOpen">Fábrica</p>
<a href="/compras" class="nav-item {% if active_page == 'compras' %}active{% endif %}">
  <span class="nav-icon">📝</span>
  <span class="nav-label" x-show="sidebarOpen">Planejamento</span>
</a>
<a href="/producao" class="nav-item {% if active_page == 'producao' %}active{% endif %}">
  <span class="nav-icon">🧑‍🍳</span>
  <span class="nav-label" x-show="sidebarOpen">Cozinha (Produção)</span>
</a>
<a href="/labels" class="nav-item {% if active_page == 'etiquetas' %}active{% endif %}">
  <span class="nav-icon">🏷️</span>
  <span class="nav-label" x-show="sidebarOpen">Lotes e Etiquetas</span>
</a>
```

---

## 5. Etapa B — Módulo de Produção (`/producao`)

### 5.1 Problema detalhado

Atualmente o fluxo de produção tem uma lacuna entre a **Ficha Técnica** (o que fazer) e o **Lote/Etiqueta** (o que foi feito). A cozinheira precisa:

1. Abrir a ficha técnica no computador do escritório.
2. Fazer manualmente a proporção (`50 porções padrão → 300 porções de hoje = × 6`).
3. Anotar cada ingrediente no caderno ou na memória.
4. Depois de produzir, lembrar de registrar o lote manualmente no sistema.

Esse fluxo gera erros de proporção, esquecimento do registro de lote e frustração operacional.

### 5.2 Solução

Criar uma nova tela `/producao` com as seguintes características:

- **Touch-friendly:** botões grandes (≥ 48px), fontes grandes (≥ 18px), pensada para tablet montado na bancada da cozinha.
- **Cálculo automático:** a cozinheira digita o número de porções desejadas, e o sistema multiplica todos os ingredientes em tempo real, sem nenhuma conta manual.
- **Geração de Lote:** ao clicar em "Finalizar Produção", o sistema registra automaticamente o lote via `POST /batches`, idêntico ao fluxo já existente em `/labels`.
- **Modo offline-first visual:** todo o cálculo é feito no frontend (Alpine.js), sem chamadas de API durante o preenchimento.

### 5.3 Interface esperada

```
┌──────────────────────────────────────────────────────────────┐
│  🧑‍🍳  Painel de Produção (Cozinha)                            │
│                                                              │
│  O que vamos fazer?                  Quantas Porções?        │
│  [ Coxinha de Frango            ▼]   [     300      ]        │
│                                       Fator: 6.00×           │
├──────────────────────────────────────────────────────────────┤
│  MASSA                                                       │
│  ──────────────────────────────────────────────────────────  │
│  ☐  Peito de Frango          18.000  kg                      │
│  ☐  Farinha de Trigo          5.500  kg                      │
│  ☐  Requeijão                 3.000  kg                      │
│                                                              │
│  👨‍🍳 Modo de Preparo: Cozinhe o frango e desfie...            │
├──────────────────────────────────────────────────────────────┤
│  RECHEIO                                                     │
│  ──────────────────────────────────────────────────────────  │
│  ☐  Caldo de Galinha          0.450  kg                      │
│  ☐  Cebola                    0.720  kg                      │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Finalizar Lote                                      │   │
│  │  Lote: L-XXXXXX   Validade: dd/mm/aaaa               │   │
│  │                                                      │   │
│  │  [   ✅  FINALIZAR PRODUÇÃO   ]                      │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 5.4 Fluxo de dados

```
GET /producao
    └── Backend busca todas as Recipes com suas sections e items
    └── Serializa para JSON (recipes_json) — embutido na página
    └── Alpine.js recebe o JSON e opera 100% no frontend

[Usuário seleciona receita + digita porções]
    └── Alpine calcula multiplier = targetPortions / rendimento_base
    └── Para cada item: qty_tela = base_qty × fc × multiplier
    └── Atualiza valores na tela em tempo real

[Usuário clica "Finalizar Produção"]
    └── HTMX POST /batches (endpoint existente, sem alteração)
    └── Campos hidden: recipe_id, product_name, batch_number, expiry_date
    └── Resposta de sucesso → toast + limpa a tela
```

### 5.5 Arquivos necessários

| Arquivo | Natureza da mudança |
|---|---|
| `main.py` | Adição da rota `GET /producao` (nova, não altera nenhuma rota existente) |
| `templates/producao.html` | Arquivo novo criado do zero |
| `templates/base.html` | Apenas o link na sidebar (já coberto pela Etapa A) |

### 5.6 Código — `main.py` (nova rota)

```python
@app.get("/producao", response_class=HTMLResponse)
async def producao_page(request: Request, db: Session = Depends(get_db)):
    """Tela de execução da cozinha (KDS — Kitchen Display System)."""
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

    return templates.TemplateResponse("producao.html", {
        "request":      request,
        "active_page":  "producao",
        "recipes":      recipes,
        "recipes_json": recipes_json,
    })
```

### 5.7 Código — `templates/producao.html` (arquivo novo)

```html
{% extends "base.html" %}
{% set active_page = "producao" %}

{% block title %}SmartFood — Módulo de Produção{% endblock %}

{% block extra_head %}
<style>
  /* Touch targets generosos para tablet */
  .kds-select  { font-size: 1.1rem; min-height: 52px; }
  .kds-input   { font-size: 1.5rem; font-weight: 700; text-align: center; color: #2563eb; }
  .kds-check   { width: 28px; height: 28px; }
  .kds-qty     { font-size: 1.6rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; }
  .kds-unit    { font-size: 1rem; color: var(--muted); margin-left: .3rem; }
  .kds-btn     {
    width: 100%; padding: 1.25rem; border-radius: .75rem;
    background: #16a34a; color: #fff;
    font-size: 1.3rem; font-weight: 700;
    border: none; cursor: pointer;
    box-shadow: 0 4px 16px rgba(22,163,74,.35);
    transition: background .15s, transform .1s;
    active:scale-95;
  }
  .kds-btn:hover  { background: #15803d; }
  .kds-btn:active { transform: scale(.97); }
  .section-header {
    background: #1e293b; color: #fff;
    padding: .5rem 1rem; font-size: .8rem;
    font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
  }
</style>
{% endblock %}

{% block content %}
<div x-data="kdsApp()" class="max-w-3xl mx-auto">

  <!-- Cabeçalho -->
  <div class="mb-6">
    <h1 class="text-3xl font-bold" style="color:var(--text)">🧑‍🍳 Painel de Produção</h1>
    <p class="mt-1" style="color:var(--muted)">
      Selecione a receita, informe as porções e separe os ingredientes com a tela.
    </p>
  </div>

  <!-- Seletor de receita + porções -->
  <div class="card p-5 mb-6" style="background:#eff6ff;border-color:#bfdbfe">
    <div class="flex flex-col md:flex-row gap-4 items-end">
      <div class="flex-1 w-full">
        <label class="text-sm font-semibold block mb-2" style="color:var(--text)">
          O que vamos produzir hoje?
        </label>
        <select x-model="selectedRecipeId"
                @change="loadRecipe()"
                class="kds-select w-full">
          <option value="">— Selecione a Receita —</option>
          <template x-for="r in allRecipes" :key="r.id">
            <option :value="r.id" x-text="r.name"></option>
          </template>
        </select>
      </div>
      <div class="w-full md:w-44">
        <label class="text-sm font-semibold block mb-2" style="color:var(--text)">
          Quantas Porções?
        </label>
        <input type="number"
               x-model.number="targetPortions"
               min="1" step="1"
               class="kds-input w-full border rounded-lg p-2"
               style="border-color:var(--border)" />
      </div>
    </div>
  </div>

  <!-- Conteúdo principal (visível após selecionar receita) -->
  <div x-show="currentRecipe" x-cloak>

    <!-- Cabeçalho da receita com fator -->
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-2xl font-bold" style="color:var(--text)"
          x-text="currentRecipe?.name"></h2>
      <span class="px-4 py-2 rounded-full font-bold text-sm"
            style="background:#dbeafe;color:#1d4ed8">
        Fator: <span x-text="multiplier().toFixed(2)"></span>×
      </span>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-5">

      <!-- Seções de ingredientes (2/3 da largura) -->
      <div class="md:col-span-2 space-y-4">
        <template x-for="sec in currentRecipe?.sections" :key="sec.name">
          <div class="card overflow-hidden">
            <div class="section-header" x-text="sec.name"></div>
            <ul class="divide-y" style="border-color:var(--border)">
              <template x-for="item in sec.items" :key="item.name">
                <li class="p-4 flex justify-between items-center">
                  <label class="flex items-center gap-3 cursor-pointer flex-1">
                    <input type="checkbox" class="kds-check rounded"
                           style="accent-color:#16a34a">
                    <span class="text-lg font-medium" style="color:var(--text)"
                          x-text="item.name"></span>
                  </label>
                  <div class="text-right flex-shrink-0">
                    <span class="kds-qty"
                          x-text="(item.base_qty * item.fc * multiplier()).toFixed(3)">
                    </span>
                    <span class="kds-unit" x-text="item.unit"></span>
                  </div>
                </li>
              </template>
            </ul>
            <div x-show="sec.instrucoes"
                 class="p-4 text-sm"
                 style="background:#fefce8;border-top:1px solid #fef08a;color:#854d0e">
              <strong>👨‍🍳 Modo de Preparo:</strong>
              <span x-text="sec.instrucoes"></span>
            </div>
          </div>
        </template>
      </div>

      <!-- Painel lateral de finalização (1/3 da largura) -->
      <div>
        <div class="card p-5 sticky top-24">
          <h3 class="font-bold mb-2" style="color:var(--text)">Finalizar Lote</h3>
          <p class="text-sm mb-4" style="color:var(--muted)">
            Ao concluir, clique abaixo para registrar o lote de rastreabilidade.
          </p>

          <div class="text-xs mb-4 space-y-1" style="color:var(--sub)">
            <p>
              📦 Receita: <strong x-text="currentRecipe?.name"></strong>
            </p>
            <p>
              🔢 Lote: <strong x-text="'L-' + Date.now().toString().slice(-6)"></strong>
            </p>
            <p>
              📅 Validade: <strong x-text="expiryDate()"></strong>
            </p>
          </div>

          <!-- HTMX POST para o endpoint existente /batches -->
          <form hx-post="/batches"
                hx-swap="none"
                @htmx:after-request="
                  $event.detail.successful && finalizeSuccess()
                ">
            <input type="hidden" name="recipe_id"
                   :value="currentRecipe?.id">
            <input type="hidden" name="product_name"
                   :value="currentRecipe?.name">
            <input type="hidden" name="batch_number"
                   :value="'L-' + Date.now().toString().slice(-6)">
            <input type="hidden" name="expiry_date"
                   :value="expiryDateISO()">
            <input type="hidden" name="weight_kg" value="0">
            <input type="hidden" name="ingredients_summary" value="">

            <button type="submit" class="kds-btn">
              ✅ Finalizar Produção
            </button>
          </form>

          <!-- Botão para marcar todos como separados -->
          <button @click="checkAll()"
                  class="w-full mt-3 py-3 rounded-lg font-semibold text-sm transition-colors"
                  style="border:1px solid var(--border);color:var(--sub);background:var(--bg)">
            ✓ Marcar Todos Separados
          </button>
        </div>
      </div>

    </div>
  </div>

  <!-- Estado vazio (nenhuma receita selecionada) -->
  <div x-show="!currentRecipe" class="card p-12 text-center">
    <p class="text-5xl mb-4">🧑‍🍳</p>
    <p class="text-lg font-semibold" style="color:var(--text)">
      Selecione uma receita para começar
    </p>
    <p class="text-sm mt-2" style="color:var(--muted)">
      Os ingredientes nas quantidades corretas aparecerão aqui.
    </p>
  </div>

</div>
{% endblock %}

{% block scripts %}
<script>
function kdsApp() {
  return {
    allRecipes: {{ recipes_json | tojson }},
    selectedRecipeId: '',
    currentRecipe:    null,
    targetPortions:   50,

    loadRecipe() {
      if (!this.selectedRecipeId) {
        this.currentRecipe = null;
        return;
      }
      this.currentRecipe = this.allRecipes.find(
        r => r.id === parseInt(this.selectedRecipeId)
      );
      if (this.currentRecipe) {
        this.targetPortions = this.currentRecipe.rendimento_base;
      }
    },

    multiplier() {
      if (!this.currentRecipe || this.currentRecipe.rendimento_base <= 0) return 1;
      return this.targetPortions / this.currentRecipe.rendimento_base;
    },

    expiryDate() {
      const d = new Date();
      d.setMonth(d.getMonth() + 3);
      return d.toLocaleDateString('pt-BR');
    },

    expiryDateISO() {
      const d = new Date();
      d.setMonth(d.getMonth() + 3);
      return d.toISOString().split('T')[0];
    },

    checkAll() {
      document.querySelectorAll('.kds-check')
        .forEach(cb => { cb.checked = true; });
    },

    finalizeSuccess() {
      toast('Lote gerado! Vá para Lotes e Etiquetas para imprimir.', 'success');
      // Reseta a tela para a próxima produção
      this.selectedRecipeId = '';
      this.currentRecipe    = null;
    },
  };
}
</script>
{% endblock %}
```

---

## 6. Critérios de Aceite

### Etapa A — Procurement Inteligente

| # | Cenário | Resultado esperado |
|---|---|---|
| A1 | Gerar lista com 2 receitas cujos ingredientes têm fornecedores cadastrados | Cards separados por fornecedor, cada um com valor total estimado |
| A2 | Fornecedor tem telefone em `contact_info` | Botão "Enviar Pedido via WhatsApp" aparece e o link abre corretamente |
| A3 | Fornecedor sem telefone cadastrado | Botão ausente; texto de alerta com link para cadastro |
| A4 | Ingrediente sem nenhuma entrada em `SupplierCatalog` | Item aparece no card "Sem Fornecedor — Cotar" |
| A5 | Lista continua sendo salva no banco (`ShoppingList`) | Confirmado via `/precos` → "Base de demanda" lista a nova lista |
| A6 | Nenhuma receita selecionada no plano | Mensagem "Nenhum insumo encontrado" (comportamento idêntico ao anterior) |

### Etapa B — Módulo de Produção

| # | Cenário | Resultado esperado |
|---|---|---|
| B1 | Acessar `/producao` sem receita selecionada | Tela vazia com instrução, sem erros |
| B2 | Selecionar receita com `rendimento_base = 50` | Campo de porções pré-preenche com `50`, fator mostra `1.00×` |
| B3 | Alterar porções para `300` | Fator muda para `6.00×`, todos os ingredientes multiplicam em tempo real |
| B4 | Clicar em "Finalizar Produção" | `POST /batches` executado, toast de sucesso exibido, tela limpa |
| B5 | Confirmar no banco | Novo `ProductionBatch` visível em `/labels` na tabela de lotes recentes |
| B6 | Receita com `instrucoes` em uma seção | Bloco amarelo de modo de preparo aparece abaixo dos ingredientes da seção |

---

## 7. Plano de Implementação

### Sequência recomendada

```
Dia 1 — Etapa A (2-3 horas)
├── Adicionar `import urllib.parse` no topo de main.py
├── Substituir endpoint POST /api/shopping-list
├── Testar manualmente: gerar lista → verificar cards → testar link WhatsApp
└── Atualizar sidebar em base.html (link /producao)

Dia 2 — Etapa B (3-4 horas)
├── Adicionar rota GET /producao em main.py
├── Criar templates/producao.html
├── Testar: selecionar receita → alterar porções → finalizar → verificar lote em /labels
└── Testar em viewport mobile (375px) e tablet (768px)
```

### Rollback

- **Etapa A:** reverter a função `generate_shopping_list` para a versão anterior (já documentada no código atual). O comportamento anterior é restaurado imediatamente.
- **Etapa B:** remover a rota `GET /producao` e o arquivo `producao.html`. Nenhum dado é perdido — `ProductionBatch` usa o endpoint `/batches` já existente.

---

## 8. Impacto Técnico Consolidado

| Item | Etapa A | Etapa B | Total |
|---|---|---|---|
| Arquivos novos | 0 | 1 (`producao.html`) | 1 |
| Arquivos alterados | 2 (`main.py`, `base.html`) | 1 (`main.py`) | 2 únicos |
| Migrations | 0 | 0 | 0 |
| Novos endpoints | 0 | 1 (`GET /producao`) | 1 |
| Endpoints alterados | 1 (`POST /api/shopping-list`) | 0 | 1 |
| Testes recomendados | 6 cenários (A1–A6) | 6 cenários (B1–B6) | 12 |

---

## 9. Ganhos de Negócio

### Para o Comprador

Antes de enviar o pedido, ele precisava ler uma lista de 50 itens misturados, descobrir manualmente quem vende cada um, ligar ou mandar mensagem de texto. Com a nova lista agrupada por fornecedor, ele abre o card da distribuidora, vê R$ 800 em compras, clica no botão e o **WhatsApp Web já abre com a lista pronta**.

### Para a Cozinheira

A ficha técnica foi feita para 50 porções. O chef mandou fazer 300 hoje. Antes ela fazia a conta no caderno, errava às vezes, perdia tempo. Com `/producao`, ela abre o tablet, seleciona a receita, digita `300` e vê instantaneamente que precisa de `18 kg` de farinha — com caixinhas para marcar o que já separou. Ao terminar, um botão registra o lote no sistema sem que ela precise ir ao computador do escritório.

---

## 10. Dependências e Pré-condições

| Condição | Responsável |
|---|---|
| Fornecedores devem ter `contact_info` preenchido com número de WhatsApp para o botão funcionar | Operador/Comprador |
| Ingredientes devem ter entradas em `SupplierCatalog` para aparecer no card correto | Operador |
| Receitas devem ter `rendimento_unidades > 0` para o fator de multiplicação funcionar | Engenheiro de Alimentos |
| `segno` instalado (já está em `requirements.txt`) | — |
| Python 3.13 + FastAPI 0.128 (já atendidos conforme `MANUAL_TESTE.md`) | — |
