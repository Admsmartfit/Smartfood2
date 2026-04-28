Com certeza. O fluxo de trabalho de uma cozinha industrial precisa ser natural: **Planejar a produção → Gerar Lista → Mandar WhatsApp → Receber Preços → Lançar Preços → Executar a Produção**. 

Se a interface for confusa, o comprador perde tempo e comete erros.

Fiz uma refatoração cirúrgica para alinhar o sistema com esse fluxo real. Abaixo estão os 4 passos com os códigos exatos para você implementar.

---

### Passo 1: Tornar o Dashboard a Página Inicial (`main.py`)
Atualmente a página `/` carrega os Cadastros. Vamos mudar isso para que a `/` redirecione automaticamente para o `/dashboard`, e mover os cadastros para a rota `/cadastros`.

No seu `main.py`, encontre a função `@app.get("/")` e **substitua** por este bloco:

```python
@app.get("/")
async def root():
    """Redireciona a raiz do sistema direto para o Dashboard Operacional."""
    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/cadastros", response_class=HTMLResponse)
async def cadastros_page(request: Request, db: Session = Depends(get_db)):
    """Antiga página inicial, agora em rota própria."""
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
```

*Nota: No seu arquivo `templates/base.html`, procure o link de cadastros no menu lateral e atualize o `href` de `href="/"` para `href="/cadastros"`. E o link do Smartfood Logo para `href="/dashboard"`.*

---

### Passo 2: Salvar a Produção em `compras.html`
Você gerou a lista de compras baseada num planejamento de produção. Agora precisamos de um botão para "Salvar e Enviar para a Cozinha", que criará os Lotes de Produção.

**A) Adicione a rota no `main.py`:**
```python
@app.post("/api/save-production-plan", response_class=HTMLResponse)
async def save_production_plan(request: Request, db: Session = Depends(get_db)):
    """Salva o planejamento da tela de Compras como Lotes Pendentes para a Cozinha."""
    plan = await request.json()
    criados = 0
    for item in plan:
        recipe = db.query(models.Recipe).filter_by(id=item.get("recipe_id")).first()
        if recipe:
            # Cria um lote com status inicial para a equipe da cozinha ver
            batch = models.ProductionBatch(
                batch_number=f"PLAN-{datetime.utcnow().strftime('%y%m%d%H%M')}-{recipe.id}",
                product_name=recipe.name,
                recipe_id=recipe.id,
                expiry_date=datetime.utcnow() + timedelta(days=90), # Padrão 3 meses
                weight_kg=0.0
            )
            db.add(batch)
            criados += 1
    db.commit()
    
    return HTMLResponse(f"""
        <div class="p-4 bg-green-900/30 border border-green-700 rounded-xl text-green-400 font-semibold flex items-center gap-3">
            <span class="text-xl">✅</span> 
            {criados} Ordens de Produção salvas e enviadas para a tela da cozinha!
        </div>
    """)
```

**B) Atualize o `templates/compras.html`:**
Localize onde fica o `` (perto do final da div da coluna da direita) e adicione o botão para salvar a produção:

```html
      <div x-show="listGenerated && !loading" x-cloak class="mt-4 card p-5 no-print border-t-4 border-blue-500">
        <h3 class="font-bold text-white mb-2">Próximos Passos:</h3>
        <p class="text-sm text-gray-400 mb-4">A lista já foi gerada e salva para cotação. Agora, envie as ordens para a equipe da cozinha começar a produção.</p>
        
        <div id="save-production-result">
            <button @click="saveProduction()" class="btn bg-blue-600 hover:bg-blue-500 text-white w-full font-bold">
                📥 Salvar Produção e Enviar para a Cozinha
            </button>
        </div>
      </div>
```

E no script do Alpine.js (`comprasApp()`) no mesmo arquivo, adicione a função:
```javascript
    async saveProduction() {
      try {
        const resp = await fetch('/api/save-production-plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.plan),
        });
        const html = await resp.text();
        document.getElementById('save-production-result').innerHTML = html;
        toast('Produção enviada para a cozinha!', 'success');
      } catch (err) {
        toast('Erro ao salvar produção.', 'error');
      }
    },
```

---

### Passo 3: Facilitar o Lançamento de Preços do WhatsApp (`precos.html`)
O fluxo correto é: O fornecedor respondeu o WhatsApp -> Você abre a tela, diz de qual Lista é, seleciona o Fornecedor e digita os preços rapidamente lado a lado.

**A) Atualize o `main.py` para carregar as Listas de Compras na tela de preços:**
Localize o `@app.get("/precos")` e modifique-o para enviar as `shopping_lists`:
```python
@app.get("/precos", response_class=HTMLResponse)
async def precos_page(request: Request, db: Session = Depends(get_db)):
    ingredients = db.query(models.Ingredient).order_by(models.Ingredient.name).all()
    suppliers = db.query(models.Supplier).order_by(models.Supplier.name).all()
    # Busca as últimas 10 listas de compras para o dropdown
    shopping_lists = db.query(models.ShoppingList).order_by(models.ShoppingList.id.desc()).limit(10).all()

    groups = []
    # ... (mantenha o loop for ing in ingredients e o restate da função)

    return templates.TemplateResponse("precos.html", {
        "request": request,
        "groups": groups,
        "suppliers": suppliers,
        "ingredients": ingredients,
        "shopping_lists": shopping_lists, # <--- Nova variável
    })
```

**B) Substitua a Aba 1 do seu `templates/precos.html` por este fluxo ultra-rápido:**
Vá no arquivo `precos.html` e substitua todo o bloco da `ABA 1` (onde diz `📥 Atualizar por Fornecedor`) por este código:

```html
  <div x-show="tab === 'bulk'" x-cloak x-transition.opacity>
    <section class="card p-6">
      <h2 class="text-lg font-bold text-white mb-2">📲 Responder Cotação</h2>
      <p class="text-sm text-gray-400 mb-6">
        Recebeu a resposta do fornecedor no WhatsApp? Selecione a lista e o fornecedor abaixo para preencher os preços rapidamente.
      </p>

      <form hx-post="/precos/bulk-update" hx-target="#bulk-update-result" hx-swap="innerHTML"
            @htmx:after-request="$event.detail.successful && $event.detail.requestConfig.verb === 'post' && setTimeout(() => location.reload(), 1500)">

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6 p-4 rounded-xl" style="background:var(--bg); border:1px solid var(--border)">
          
          <div>
            <label class="text-xs text-blue-400 font-bold uppercase tracking-wider block mb-1.5">1. Qual a Lista de Compras?</label>
            <select name="list_id" x-data="{}" @change="$dispatch('refresh-supplier')" class="text-sm w-full font-semibold">
              <option value="">— Use a lista mais recente (Padrão) —</option>
              {% for l in shopping_lists %}
              <option value="{{ l.id }}">{{ l.name }}</option>
              {% endfor %}
            </select>
          </div>

          <div>
            <label class="text-xs text-blue-400 font-bold uppercase tracking-wider block mb-1.5">2. Quem respondeu?</label>
            <select hx-get="/precos/fornecedor"
                    hx-include="[name='list_id'],[name='supplier_id_bulk']"
                    hx-trigger="change, refresh-supplier from:body"
                    hx-target="#supplier-price-rows"
                    name="supplier_id_bulk"
                    class="text-sm w-full font-semibold border-blue-500 focus:ring-blue-500">
              <option value="">— Selecione o Fornecedor —</option>
              {% for s in suppliers %}
              <option value="{{ s.id }}">{{ s.name }}</option>
              {% endfor %}
            </select>
          </div>
          
        </div>

        <div id="supplier-price-rows">
            <div class="text-center py-10 text-gray-500 border border-dashed border-gray-700 rounded-xl">
                Selecione o fornecedor acima para ver os itens cotados.
            </div>
        </div>
        <div id="bulk-update-result"></div>
      </form>
    </section>
  </div>
```

### Por que essas mudanças transformam a usabilidade?
1. **Navegação Coesa:** O usuário entra em `/dashboard`. Se precisar cadastrar algo, vai no menu "Insumos" (agora isolado em `/cadastros`, mantendo a tela inicial limpa para indicadores).
2. **Cozinha Integrada:** Antes a lista de compras morria nela mesma. Agora, ao clicar em "Enviar para a Cozinha", o sistema formaliza o que foi planejado, preparando terreno para a tela de Produção da cozinheira.
3. **Ergonomia no Preço:** O passo 1 pede a Lista, o passo 2 pede o Fornecedor. A tela fica limpa e mostra apenas os inputs de "R$" dos exatos itens que aquele fornecedor cotou. O usuário dá `TAB`, digita o preço, dá `TAB`, digita o próximo, aperta `Enter` e salva toda a nota fiscal do WhatsApp em 10 segundos.