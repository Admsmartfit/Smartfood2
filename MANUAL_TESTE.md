# Manual de Teste — SmartFood Ops 360

**Ambiente:** Windows 11 · Python 3.13 · localhost:8000

---

## Pré-requisitos (já atendidos nesta máquina)

| Componente | Versão instalada |
|---|---|
| Python | 3.13.9 |
| FastAPI | 0.128.0 |
| Uvicorn | 0.40.0 |
| SQLAlchemy | 2.0.46 |
| Jinja2 | 3.1.6 |
| segno (QR) | 1.6.6 |

---

## PASSO 1 — Iniciar o servidor

Abra o **Prompt de Comando** (tecle `Win + R`, digite `cmd`, Enter).

```
cd C:\Users\ralan\Smartfood2
run_app.bat
```

Aguarde a mensagem:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> Deixe essa janela aberta durante todo o teste. Para encerrar depois: `Ctrl + C`.

---

## PASSO 2 — Módulo de Insumos (tela raiz)

Abra o navegador e acesse: **http://localhost:8000**

### 2.1 Cadastrar ingrediente

1. Preencha **Nome:** `Peito de Frango`
2. Preencha **Unidade:** `kg`
3. Clique **Cadastrar Ingrediente**
4. ✅ Esperado: o item aparece na lista logo abaixo do botão, sem recarregar a página.

Repita para um segundo ingrediente: `Farinha de Trigo` / `kg`

### 2.2 Cadastrar marcas (fabricantes)

1. Selecione o ingrediente **Peito de Frango**
2. **Marca:** `Seara` · **Rendimento:** `78` · **Qualidade:** `5`
3. Clique **Cadastrar Marca**
4. ✅ Esperado: confirmação inline.

Repita para uma segunda marca do mesmo ingrediente:

- **Marca:** `Frisa` · **Rendimento:** `82` · **Qualidade:** `4`

### 2.3 Cadastrar fornecedor

1. **Nome:** `Distribuidora São Paulo` · **Contato:** `(11) 9999-0000`
2. Clique **Cadastrar Fornecedor** — ✅ confirmação inline.

### 2.4 Vincular preços no catálogo

1. **Fornecedor:** Distribuidora São Paulo
2. **Ingrediente:** Peito de Frango → o dropdown de marcas carrega automaticamente (HTMX)
3. **Marca:** Seara · **Preço:** `18.90`
4. Clique **Vincular e Salvar Preço**
5. ✅ Esperado: nova linha aparece na tabela do catálogo.

Repita para Frisa com preço `16.50`.

> **Teste mobile:** Redimensione o navegador para menos de 640px de largura.
> A tabela do catálogo deve virar **cards** empilhados, com o nome da coluna antes de cada valor.

---

## PASSO 3 — Ficha Técnica

Acesse: **http://localhost:8000/ficha-tecnica**

### 3.1 Criar receita básica

1. **Nome:** `Coxinha de Frango`
2. **Markup:** `3.0`
3. **Margem Mínima:** `25`

### 3.2 Adicionar insumo com troca de marca

1. Clique **+ Adicionar Insumo** dentro da seção "Massa"
2. Selecione **Peito de Frango** no dropdown de insumo
3. ✅ Esperado: o dropdown **Marca** é habilitado com Seara e Frisa.
4. Selecione **Seara**
5. ✅ Esperado: o campo **FC** preenche automaticamente com `1.282` (= 100 / 78) e o **Preço** com `18.90`
6. Troque para **Frisa**
7. ✅ Esperado: FC muda para `1.220` (= 100 / 82) e Preço para `16.50`
8. Preencha **Qtde:** `0.5` · **FCoc:** `0.85`
9. ✅ Esperado: coluna **Custo** atualiza em tempo real.

### 3.3 Verificar semáforo de margem

Com os valores acima, observe o bloco **Margem de Lucro** no painel direito:

- 🟢 Verde → margem ≥ 25%
- 🟡 Amarelo → entre 20% e 25%
- 🔴 Vermelho → abaixo de 20%

### 3.4 Salvar a ficha

1. Clique **💾 Salvar Ficha Técnica**
2. ✅ Esperado: mensagem de confirmação com o ID gerado, ex.:

```
✅ "Coxinha de Frango" salva! (ID 1) — visível no Dashboard.
```

---

## PASSO 4 — Dashboard de Margem

Acesse: **http://localhost:8000/dashboard**

### 4.1 Visualizar alertas (limite padrão 20%)

- ✅ Esperado: KPIs no topo mostram o total de receitas.
- Se a margem da Coxinha estiver abaixo de 20%, ela aparece em um card vermelho/amarelo.

### 4.2 Ajustar o limite

1. Altere o campo **Limite de margem** para `50`
2. Clique **Aplicar**
3. ✅ Esperado: a URL muda para `/dashboard?limite=50` e mais receitas entram na lista de alertas.

### 4.3 Verificar seção "Receitas OK"

- Clique em **Receitas OK (N) ▼ expandir** no final da página
- ✅ Esperado: cards menores com barra verde expandem abaixo.

---

## PASSO 5 — Etiquetas

Acesse: **http://localhost:8000/labels**

### 5.1 Criar um template

1. **Nome:** `Etiqueta Padrão 62mm`
2. **Largura:** `62` · **Altura:** `40`
3. **Tipo:** `ZPL — Zebra`
4. **IP da Impressora:** deixe em branco (sem impressora real)
5. Clique em **Preencher padrão** → o campo JSON é preenchido automaticamente
6. Clique **Criar Template**
7. ✅ Esperado: o template aparece na lista **Templates Salvos**.

### 5.2 Visualizar preview

1. Clique no template criado na lista
2. ✅ Esperado: no centro aparece a etiqueta simulada — fundo branco, fonte monoespaçada, QR Code no canto direito.
3. Troque o dropdown **Dados de exemplo** para um lote, se já houver (ou deixe em branco para ver dados fictícios).

### 5.3 Ver o comando ZPL

1. Com o template selecionado, clique **Ver Comando ZPL/TSPL**
2. ✅ Esperado: bloco de código preto com os comandos `^XA … ^XZ` exibidos abaixo.

### 5.4 Registrar um lote de produção

1. **Nº do Lote:** `L-2024-001`
2. **Produto:** `Coxinha de Frango`
3. **Validade:** selecione uma data futura (ex: 3 dias à frente)
4. **Peso:** `0.120`
5. **Ingredientes:** `Frango, Farinha, Requeijão`
6. **URL Tutorial:** `https://exemplo.com/tutorial`
7. **URL Promoção:** `https://exemplo.com/promo`
8. Clique **Registrar Lote**
9. ✅ Esperado: nova linha aparece na tabela **Lotes Recentes** com um link **QR ↗**.

### 5.5 Testar QR Code dinâmico

1. Clique em **QR ↗** do lote recém-criado
2. ✅ Se a validade for > 3 dias: redireciona para `https://exemplo.com/tutorial`
3. Crie um segundo lote com validade **hoje ou amanhã** e clique em seu **QR ↗**
4. ✅ Esperado: redireciona para `https://exemplo.com/promo`

---

## PASSO 6 — Teste mobile-first (todos os módulos)

Abra o DevTools do navegador com `F12`, clique no ícone de dispositivo móvel
(ou `Ctrl + Shift + M`) e selecione **iPhone SE** (375px).

| Tela | O que verificar |
|---|---|
| `/` | Tabela catálogo → cards empilhados com labels |
| `/ficha-tecnica` | BOM vira cards verticais; sidebar fica abaixo do builder |
| `/labels` | Tabela de lotes → cards; todos os botões com altura visível ≥ 48px |
| `/dashboard` | Grid de KPIs 2 colunas; cards de alerta empilhados |

---

## PASSO 7 — Verificar o banco de dados (opcional)

Instale o [DB Browser for SQLite](https://sqlitebrowser.org/) e abra:

```
C:\Users\ralan\Smartfood2\smartfood.db
```

Tabelas esperadas:

```
ingredients            ingredient_manufacturers   suppliers
supplier_catalog       recipes                   recipe_sections
bom_items              label_templates           production_batches
```

---

## Problemas comuns

| Sintoma | Solução |
|---|---|
| `Address already in use` ao iniciar | No cmd: `netstat -ano \| findstr :8000` → anote o PID → `taskkill /PID <número> /F` |
| Página em branco / erro 500 | Veja a janela do cmd — o FastAPI imprime o traceback completo |
| Dropdown de marcas não carrega | Certifique-se de ter cadastrado pelo menos uma marca para o ingrediente em `/` |
| QR não redireciona | A URL precisa ser completa com `https://` — URLs sem protocolo são ignoradas |
| `ModuleNotFoundError: segno` | Execute `pip install segno` no cmd dentro da pasta do projeto |

---

## Resumo dos URLs

| Módulo | URL |
|---|---|
| Insumos & Fornecedores | http://localhost:8000 |
| Ficha Técnica | http://localhost:8000/ficha-tecnica |
| Etiquetas | http://localhost:8000/labels |
| Dashboard | http://localhost:8000/dashboard |
| QR redirect (lote N) | http://localhost:8000/qr/1 |
| Docs automáticas da API | http://localhost:8000/docs |
