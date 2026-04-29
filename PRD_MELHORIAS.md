Para atender à sua necessidade de gerenciar múltiplos fornecedores para um mesmo insumo e permitir a escolha de para quem enviar o pedido via WhatsApp, precisamos tornar a lista de compras **interativa**.

A melhor prática de mercado para sistemas de *procurement* (como o *MarketMan*) é agrupar por fornecedor sugerido (o mais barato), mas permitir a **re-atribuição rápida** de itens entre fornecedores antes de fechar o pedido.

Aqui estão os passos para implementar essa funcionalidade:

### 1. Atualizar o Backend (`main.py`)
Precisamos modificar a lógica de geração da lista para que ela identifique **todos** os fornecedores que vendem cada ingrediente, e não apenas o mais barato.

Substitua a função `generate_shopping_list` no seu `main.py`:

```python
@app.post("/api/shopping-list", response_class=HTMLResponse)
async def generate_shopping_list(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    agg = {} # Lógica de agregação de ingredientes por ID
    
    # ... (mantenha o loop de agregação de porções igual ao anterior) ...

    # 2. Busca TODOS os fornecedores para cada ingrediente do catálogo
    for ing_id, data in agg.items():
        # Busca todas as entradas no catálogo para este ingrediente
        catalog_entries = db.query(models.SupplierCatalog).filter_by(ingredient_id=ing_id).all()
        
        data["alternatives"] = []
        for entry in catalog_entries:
            data["alternatives"].append({
                "supplier_id": str(entry.supplier_id),
                "supplier_name": entry.supplier.name,
                "supplier_phone": entry.supplier.contact_info or "",
                "price": entry.last_price or 0.0,
                "brand": entry.manufacturer.brand_name if entry.manufacturer else "Genérica"
            })
        
        # Ordena por preço e define o primeiro como padrão
        data["alternatives"].sort(key=lambda x: x["price"])
        if data["alternatives"]:
            data["selected_supplier"] = data["alternatives"][0]
        else:
            data["selected_supplier"] = {"supplier_id": "0", "supplier_name": "Sem Fornecedor", "supplier_phone": "", "price": 0.0}

    # 3. Organiza os dados para o componente Alpine.js
    # Passamos os dados processados para um template ou geramos o HTML compatível
    # Aqui vamos usar uma abordagem onde o Alpine.js gerencia a lista no cliente
    return templates.TemplateResponse("fragments/shopping_list_interactive.html", {
        "request": request,
        "items": agg,
        "suppliers": {s.id: s.name for s in db.query(models.Supplier).all()}
    })
```

### 2. Novo Fragmento Interativo (`templates/fragments/shopping_list_interactive.html`)
Este novo fragmento usa o **Alpine.js** para permitir que o usuário mova itens entre os fornecedores em tempo real antes de enviar o WhatsApp.

```html
<div x-data="{
    // Dados injetados do servidor
    orderItems: {{ items | tojson | safe }},
    
    // Agrupar itens pelo fornecedor selecionado
    get grouped() {
        let groups = {};
        Object.values(this.orderItems).forEach(item => {
            let sId = item.selected_supplier.supplier_id;
            if (!groups[sId]) {
                groups[sId] = {
                    name: item.selected_supplier.supplier_name,
                    phone: item.selected_supplier.supplier_phone,
                    items: []
                };
            }
            groups[sId].items.push(item);
        });
        return groups;
    },

    // Gerar link do WhatsApp dinamicamente
    getWhatsAppLink(supplier) {
        let text = 'Olá ' + supplier.name + '! Gostaria de fazer o seguinte pedido:\n\n';
        supplier.items.forEach(i => {
            text += '- ' + i.qty.toFixed(2) + ' ' + i.unit + ' de ' + i.name + '\n';
        });
        return 'https://wa.me/' + supplier.phone.replace(/\D/g,'') + '?text=' + encodeURIComponent(text);
    }
}" class="space-y-6">

    <template x-for="(group, sId) in grouped" :key="sId">
        <div class="card p-5 border-l-4" :class="sId === '0' ? 'border-red-500' : 'border-blue-500'">
            <div class="flex justify-between items-center mb-4">
                <h3 class="font-bold text-lg text-white" x-text="group.name"></h3>
                <span class="text-xs text-gray-500" x-text="group.items.length + ' itens'"></span>
            </div>

            <ul class="divide-y divide-gray-800">
                <template x-for="item in group.items" :key="item.name">
                    <li class="py-3 flex flex-col gap-2">
                        <div class="flex justify-between">
                            <span class="text-sm font-medium text-gray-200" x-text="item.name"></span>
                            <span class="font-mono text-sm text-blue-400" x-text="item.qty.toFixed(2) + ' ' + item.unit"></span>
                        </div>
                        
                        <div x-show="item.alternatives.length > 1" class="flex items-center gap-2">
                            <label class="text-[10px] text-gray-500 uppercase">Trocar fornecedor:</label>
                            <select x-model="item.selected_supplier" class="text-xs p-1 bg-slate-900 border-slate-700 rounded">
                                <template x-for="alt in item.alternatives" :key="alt.supplier_id">
                                    <option :value="alt" x-text="alt.supplier_name + ' (R$ ' + alt.price.toFixed(2) + ')'"></option>
                                </template>
                            </select>
                        </div>
                    </li>
                </template>
            </ul>

            <div x-show="sId !== '0' && group.phone" class="mt-4 pt-4 border-t border-gray-800">
                <a :href="getWhatsAppLink(group)" target="_blank" 
                   class="btn btn-primary btn-full bg-green-600 hover:bg-green-500 text-xs h-10">
                    📱 Enviar Lista para <span x-text="group.name" class="ml-1"></span>
                </a>
            </div>
        </div>
    </template>
</div>
```

### O que essa melhoria entrega:
1.  **Flexibilidade Total:** Se um fornecedor estiver sem estoque, o usuário simplesmente muda o item para outro fornecedor no dropdown e o botão do WhatsApp se atualiza na hora.
2.  **Visibilidade de Preço:** O dropdown de "Trocar Fornecedor" já mostra o preço de cada um, permitindo decidir se vale a pena pagar um pouco mais para centralizar a entrega.
3.  **WhatsApp Inteligente:** O link não é gerado uma única vez; ele é uma função reativa do Alpine.js que recalcula o texto da mensagem toda vez que você move um item de um card para o outro.
4.  **Organização:** Itens que não possuem nenhum fornecedor cadastrado são automaticamente isolados em um card de alerta "Sem Fornecedor".

**Dica de implementação:** Certifique-se de que o telefone do fornecedor no cadastro inclua o código do país (ex: 5511999999999) para que o link do WhatsApp funcione corretamente sem precisar de edição manual.