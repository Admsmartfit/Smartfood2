A sua necessidade reflete exatamente como um setor de **Procurement (Compras)** profissional opera! Você não envia um pedido de compra cego; você faz uma **Cotação (RFQ - Request for Quotation)**. 

Se você precisa de Farinha e de Frango, e tem 3 fornecedores diferentes que vendem isso, você quer poder enviar a cotação para os 3, ou escolher enviar a Farinha só para um e o Frango para outro.

Para resolver isso, vou mudar a lógica de inteligência do seu sistema. Em vez de o sistema escolher "um único fornecedor" e te prender a ele, o sistema vai gerar um **Card para cada fornecedor compatível**. Dentro desse card, todos os itens que ele vende terão um **Check (caixa de seleção)**. Assim, você marca/desmarca o que quer cotar com ele, e o botão do WhatsApp se atualiza na mesma hora!

Aqui está a substituição completa da rota no seu `main.py`.

### 🛠️ Como implementar:

Abra o arquivo `main.py`, encontre a função `@app.post("/api/shopping-list")` inteira e **substitua por este código abaixo**:

```python
import json # Garanta que isso está no topo do seu main.py se já não estiver

@app.post("/api/shopping-list", response_class=HTMLResponse)
async def generate_shopping_list(request: Request, db: Session = Depends(get_db)):
    """Gera lista agrupada por TODOS os Fornecedores compatíveis para envio de Cotações."""
    body = await request.json()
    agg: dict[int, dict] = {}
    
    # 1. Agrupa os ingredientes e multiplica pelas porções
    for entry in body:
        recipe_id = int(entry.get("recipe_id", 0))
        portions  = float(entry.get("portions", 1) or 1)
        recipe = db.query(models.Recipe).filter_by(id=recipe_id).first()
        if not recipe: continue
        
        base_portions = recipe.rendimento_unidades if recipe.rendimento_unidades else 1
        multiplier = portions / base_portions

        for section in recipe.sections:
            for item in section.items:
                ing = item.ingredient
                if not ing: continue
                qty_bruto = item.quantity * item.correction_factor * multiplier
                if ing.id not in agg:
                    agg[ing.id] = {
                        "name": ing.name, "unit": ing.unit, "qty": 0.0,
                        "category": ing.category or "Outros",
                        "alternatives": []
                    }
                agg[ing.id]["qty"] += qty_bruto

    if not agg:
        return HTMLResponse('<p class="text-center text-gray-500 py-6">Nenhum insumo encontrado nas receitas.</p>')

    # 2. Mapeia TODOS os fornecedores elegíveis para cada item
    all_suppliers = db.query(models.Supplier).all()
    
    for ing_id, data in agg.items():
        # Busca o que já está no catálogo com preços
        catalog_entries = db.query(models.SupplierCatalog).filter_by(ingredient_id=ing_id).all()
        cat_sup_ids = {c.supplier_id: c.last_price for c in catalog_entries}
        
        for sup in all_suppliers:
            sup_cats = [c.category for c in sup.supplier_categories]
            # Se o fornecedor já tem preço tabelado OU se atende a categoria do produto
            if sup.id in cat_sup_ids or data["category"] in sup_cats:
                data["alternatives"].append({
                    "supplier_id": str(sup.id),
                    "supplier_name": sup.name,
                    "supplier_phone": sup.contact_info or "",
                    "price": cat_sup_ids.get(sup.id, 0.0)
                })

    # 3. Salva a lista de compras no Banco de Dados
    s_list = models.ShoppingList(name=f"Cotação gerada em {datetime.utcnow().strftime('%d/%m/%Y às %H:%M')}")
    db.add(s_list)
    db.flush()
    for ing_id, data in agg.items():
        db.add(models.ShoppingListItem(list_id=s_list.id, ingredient_id=ing_id, qty=data["qty"]))
    db.commit()

    # 4. Gera a interface Interativa usando Alpine.js (Sem precisar de arquivos novos)
    items_json = json.dumps(agg)
    
    html = f"""
    <div x-data="{{
        orderItems: {items_json},
        groups: {{}},
        init() {{
            let g = {{}};
            Object.values(this.orderItems).forEach(item => {{
                // Se nenhum fornecedor atende este item
                if (item.alternatives.length === 0) {{
                    if (!g['0']) g['0'] = {{ name: 'Sem Fornecedor Compatível', phone: '', items: [] }};
                    g['0'].items.push({{ ...item, selected: true }});
                    return;
                }}
                // Distribui o item para os cards de TODOS os fornecedores que podem vendê-lo
                item.alternatives.forEach(alt => {{
                    if (!g[alt.supplier_id]) {{
                        g[alt.supplier_id] = {{
                            name: alt.supplier_name,
                            phone: alt.supplier_phone,
                            items: []
                        }};
                    }}
                    g[alt.supplier_id].items.push({{
                        name: item.name,
                        qty: item.qty,
                        unit: item.unit,
                        price: alt.price,
                        selected: true // Começa com o checkbox marcado
                    }});
                }});
            }});
            this.groups = g;
        }},
        countSelected(group) {{
            return group.items.filter(i => i.selected).length;
        }},
        getWhatsAppLink(group) {{
            let text = 'Olá *' + group.name + '*! Pode me passar a cotação atualizada para os itens abaixo?\\n\\n';
            group.items.filter(i => i.selected).forEach(i => {{
                text += '▫️ ' + i.qty.toFixed(2) + ' ' + i.unit + ' de ' + i.name + '\\n';
            }});
            text += '\\nAguardo o retorno. Obrigado!';
            let phone = group.phone ? group.phone.replace(/\\D/g,'') : '';
            return 'https://wa.me/' + phone + '?text=' + encodeURIComponent(text);
        }}
    }}" class="space-y-6">
        
        <div class="p-4 bg-green-900/30 border border-green-700 rounded-xl text-green-400 font-semibold flex items-center gap-3">
            <span class="text-xl">✅</span> Lista processada! Marque os itens que deseja cotar com cada fornecedor.
        </div>

        <template x-for="(group, sId) in groups" :key="sId">
            <div class="card overflow-hidden border border-slate-700 shadow-md">
                <div class="bg-slate-800 px-5 py-4 border-b border-slate-700 flex justify-between items-center">
                    <div>
                        <h3 class="font-bold text-lg text-white" x-text="group.name"></h3>
                        <p class="text-xs text-slate-400" x-text="group.phone || 'Sem telefone cadastrado'"></p>
                    </div>
                    <span class="bg-slate-700 text-slate-300 px-3 py-1 rounded-full text-xs font-bold" x-text="countSelected(group) + ' itens selecionados'"></span>
                </div>

                <ul class="divide-y divide-slate-800 px-5">
                    <template x-for="(item, idx) in group.items" :key="idx">
                        <li class="py-3 flex justify-between items-center hover:bg-slate-800/30 cursor-pointer" @click="item.selected = !item.selected">
                            <label class="flex items-center gap-3 cursor-pointer flex-1">
                                <input type="checkbox" x-model="item.selected" class="w-5 h-5 rounded border-slate-600 bg-slate-900 text-blue-600 focus:ring-blue-500">
                                <span class="text-sm font-medium" :class="item.selected ? 'text-slate-200' : 'text-slate-600 line-through'" x-text="item.name"></span>
                            </label>
                            <span class="font-mono text-sm" :class="item.selected ? 'text-blue-400' : 'text-slate-600'" x-text="item.qty.toFixed(2) + ' ' + item.unit"></span>
                        </li>
                    </template>
                </ul>

                <div class="px-5 py-4 bg-slate-900 border-t border-slate-800" x-show="sId !== '0'">
                    <a :href="getWhatsAppLink(group)" target="_blank" 
                       class="btn bg-green-600 hover:bg-green-500 text-white w-full text-sm font-bold flex justify-center items-center gap-2"
                       :class="countSelected(group) === 0 ? 'opacity-50 pointer-events-none' : ''">
                        📱 Enviar Cotação para <span x-text="group.name"></span>
                    </a>
                </div>
            </div>
        </template>
    </div>
    """
    return HTMLResponse(html)
```

### 🧠 Como essa mágica funciona agora:
1. Ao gerar a lista, o sistema exibe **vários cartões** – um para cada fornecedor que atenda a essas categorias/itens.
2. Se você precisar comprar "Frango", e o fornecedor **A** e o **B** venderem carne, o frango vai aparecer nos dois cartões.
3. Se você quiser testar qual o melhor preço do dia, basta **deixar marcado** no fornecedor A e no fornecedor B e clicar no botão do WhatsApp de ambos.
4. Se você decidir: *"O frango vou cotar só com o fornecedor B porque ele entrega hoje"*, basta desmarcar o checkbox do frango no cartão do fornecedor A.
5. O botão do WhatsApp **se reescreve automaticamente em tempo real**. Ele só manda no texto a lista dos ingredientes cujo "check" estiver marcado para aquele fornecedor!