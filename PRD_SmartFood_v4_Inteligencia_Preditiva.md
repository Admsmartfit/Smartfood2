# PRD — SmartFood Ops 360 v4.0
## Módulo de Inteligência Preditiva: Produção Antecipada & Análise de Consumo do Cliente

**Sistema:** SmartFood Ops 360  
**Versão:** 4.0 — Módulo de Inteligência  
**Data:** Maio 2026  
**Depende de:** v3.0 (Usuários, Portal Cliente, QR Code)  
**Princípio-guia:** Zero dependência de IA externa. Toda inteligência é calculada no backend Python com dados já existentes em `SalesOrder` e `SalesOrderItem`. Sem bibliotecas de ML — apenas estatística descritiva simples.

---

## Índice

1. [Diagnóstico e Motivação](#1-diagnóstico-e-motivação)
2. [Visão Geral do Módulo](#2-visão-geral-do-módulo)
3. [Fontes de Dados Disponíveis](#3-fontes-de-dados-disponíveis)
4. [Motor de Cálculo — Lógica Central](#4-motor-de-cálculo--lógica-central)
5. [Etapa D — Painel de Inteligência de Produção](#5-etapa-d--painel-de-inteligência-de-produção)
6. [Etapa E — Análise de Consumo para o Cliente](#6-etapa-e--análise-de-consumo-para-o-cliente)
7. [Etapa F — Sugestão de Pedido Inteligente no Portal](#7-etapa-f--sugestão-de-pedido-inteligente-no-portal)
8. [Requisitos de Design](#8-requisitos-de-design)
9. [Especificação Técnica Completa](#9-especificação-técnica-completa)
10. [Critérios de Aceite](#10-critérios-de-aceite)
11. [Plano de Implementação](#11-plano-de-implementação)
12. [Impacto Técnico Consolidado](#12-impacto-técnico-consolidado)

---

## 1. Diagnóstico e Motivação

### 1.1 O Problema Atual

A fábrica opera de forma **reativa**: produz quando o estoque zerou ou quando o cliente já está sem produto. Isso gera dois cenários ruins de forma alternada:

**Cenário A — Ruptura de Estoque:**
> Cliente liga às 10h: "Preciso de 200 coxinhas para hoje à tarde." Fábrica não tem estoque. Produção emergencial, qualidade comprometida, cliente insatisfeito.

**Cenário B — Superprodução:**
> Fábrica produz 500 coxinhas "para garantir". Cliente pediu menos do que o esperado no mês. Produto vence, descarte, prejuízo direto.

### 1.2 A Oportunidade

Os dados para resolver ambos os cenários já estão no banco de dados:
- `SalesOrder` — todo pedido com data e valor total
- `SalesOrderItem` — cada produto, quantidade e preço unitário por pedido
- `ProductionBatch` — histórico de lotes produzidos com data e receita

O que falta é **transformar esses dados em decisões concretas** para dois públicos:

1. **Time de Produção:** *"O que produzir esta semana? Quanto? Qual produto está crescendo em demanda?"*
2. **Cliente B2B (Bar/Restaurante):** *"Quando devo pedir? Quanto vou precisar? Meu consumo está subindo ou caindo?"*

### 1.3 Filosofia do Motor de Inteligência

Nenhuma biblioteca de IA ou ML é necessária. Toda a lógica é **estatística descritiva simples**, implementada em Python puro:

| Técnica | Aplicação |
|---|---|
| Média Móvel Simples (MMS) | Suavizar variações pontuais de consumo |
| Taxa de Crescimento Percentual | Comparar períodos: semana vs. semana anterior |
| Dias de Cobertura de Estoque | Calcular urgência de produção |
| Desvio padrão simples | Detectar sazonalidade / picos |
| Projeção linear básica | Estimar consumo dos próximos 7/14/30 dias |

---

## 2. Visão Geral do Módulo

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MÓDULO DE INTELIGÊNCIA v4.0                          │
│                                                                         │
│  ┌──────────────────────────────────┐  ┌───────────────────────────┐   │
│  │  ETAPA D                         │  │  ETAPA E + F              │   │
│  │  Painel de Inteligência          │  │  Portal do Cliente        │   │
│  │  de Produção                     │  │                           │   │
│  │  /inteligencia                   │  │  /loja/consumo            │   │
│  │                                  │  │  /loja (+ sugestões)      │   │
│  │  Para: Admin / Produção          │  │                           │   │
│  │                                  │  │  Para: Cliente B2B        │   │
│  │  ┌──────────────────────────┐   │  │                           │   │
│  │  │ 🚨 Produzir HOJE        │   │  │  ┌───────────────────────┐│   │
│  │  │ Coxinha de Frango       │   │  │  │ Seu consumo médio:    ││   │
│  │  │ Estoque: 2 dias         │   │  │  │ 3,2 pct/semana        ││   │
│  │  │ Demanda: 48/semana      │   │  │  │ ↑ +18% vs. mês ant.   ││   │
│  │  │ Produzir: 150 un.       │   │  │  │                       ││   │
│  │  └──────────────────────────┘   │  │  │ [Pedir 4 pacotes →]   ││   │
│  │                                  │  │  └───────────────────────┘│   │
│  │  ┌──────────────────────────┐   │  │                           │   │
│  │  │ ⚠️ Planejar esta semana  │   │  │  Gráfico consumo mensal   │   │
│  │  │ Bolinha de Queijo        │   │  │  Gráfico por produto      │   │
│  │  │ Estoque: 5 dias         │   │  │  Tendência: crescendo ↑   │   │
│  │  │ Demanda: 22/semana      │   │  │                           │   │
│  │  └──────────────────────────┘   │  └───────────────────────────┘   │
│  └──────────────────────────────────┘                                   │
│                                                                         │
│  Motor de Cálculo: intelligence_engine.py (Python puro, sem ML)        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Fontes de Dados Disponíveis

### 3.1 Tabelas Existentes Utilizadas

**`sales_orders`**
```
id | customer_id | order_date | status | total_amount | notes
```
Dados relevantes: `order_date` (quando pediu), `customer_id` (quem pediu), `status` (apenas DELIVERED conta como consumo real).

**`sales_order_items`**
```
id | order_id | recipe_id | quantity | unit_price
```
Dados relevantes: `recipe_id` (qual produto), `quantity` (quantos pacotes), `unit_price`.

**`recipes`**
```
id | name | rendimento_unidades | current_stock_units
```
Dados relevantes: `rendimento_unidades` (unidades por lote/pacote), `current_stock_units` (estoque atual).

**`production_batches`**
```
id | recipe_id | production_date | expiry_date | weight_kg
```
Dados relevantes: `production_date` e `recipe_id` — histórico do que foi produzido e quando.

### 3.2 Períodos de Análise

| Janela | Uso |
|---|---|
| Últimos 7 dias | Demanda imediata / urgência de produção |
| Últimos 30 dias | Tendência mensal / comparativo |
| Últimos 90 dias | Sazonalidade / média de longo prazo |
| Semana atual vs. semana anterior | Taxa de crescimento semanal |
| Mês atual vs. mês anterior | Taxa de crescimento mensal |

### 3.3 Regra de Negócio — O que conta como "consumo real"

Apenas pedidos com `status = 'DELIVERED'` entram nos cálculos. Pedidos `PENDING` ou `CANCELED` são excluídos. Isso garante que as sugestões se baseiem no consumo efetivamente realizado, não em intenções.

---

## 4. Motor de Cálculo — Lógica Central

### 4.1 Arquivo: `intelligence_engine.py`

Arquivo Python puro, sem dependências externas além de `datetime` e `collections`. É chamado pelas rotas do FastAPI e retorna dicionários prontos para os templates Jinja2.

### 4.2 Função: `calcular_demanda_produto(recipe_id, db, janela_dias=30)`

```python
def calcular_demanda_produto(recipe_id: int, db: Session, janela_dias: int = 30) -> dict:
    """
    Calcula métricas de demanda para um produto específico no período informado.
    
    Retorna:
    {
        "recipe_id": int,
        "recipe_name": str,
        "total_unidades_vendidas": float,   # unidades (não pacotes) no período
        "media_diaria": float,              # unidades/dia
        "media_semanal": float,             # unidades/semana
        "dias_com_pedido": int,             # dias com ao menos 1 pedido
        "pico_semanal": float,              # maior volume em uma semana
        "minimo_semanal": float,            # menor volume em uma semana
        "semanas_com_dados": int,           # semanas no período
    }
    """
    desde = datetime.utcnow() - timedelta(days=janela_dias)
    
    # Busca itens de pedidos ENTREGUES no período
    itens = (
        db.query(SalesOrderItem)
        .join(SalesOrder)
        .filter(
            SalesOrderItem.recipe_id == recipe_id,
            SalesOrder.status == "DELIVERED",
            SalesOrder.order_date >= desde,
        )
        .all()
    )
    
    # Agrega por semana para calcular variação
    semanas: dict[str, float] = {}
    total = 0.0
    for item in itens:
        semana_key = item.order.order_date.strftime("%Y-W%W")
        semanas[semana_key] = semanas.get(semana_key, 0) + item.quantity
        total += item.quantity
    
    valores_semanais = list(semanas.values()) if semanas else [0]
    media_diaria = total / janela_dias if janela_dias > 0 else 0
    
    return {
        "recipe_id": recipe_id,
        "total_unidades_vendidas": total,
        "media_diaria": round(media_diaria, 2),
        "media_semanal": round(media_diaria * 7, 2),
        "dias_com_pedido": len(set(
            item.order.order_date.date() for item in itens
        )),
        "pico_semanal": max(valores_semanais),
        "minimo_semanal": min(valores_semanais),
        "semanas_com_dados": len(semanas),
    }
```

### 4.3 Função: `calcular_taxa_crescimento(recipe_id, db, customer_id=None)`

```python
def calcular_taxa_crescimento(
    recipe_id: int, 
    db: Session, 
    customer_id: int = None
) -> dict:
    """
    Compara o consumo do período atual com o anterior (semana vs. semana, mês vs. mês).
    
    Se customer_id informado: analisa apenas pedidos daquele cliente.
    Se não informado: analisa demanda total de todos os clientes.
    
    Retorna:
    {
        "semana_atual": float,
        "semana_anterior": float,
        "variacao_semanal_pct": float,      # positivo = crescendo, negativo = caindo
        "tendencia_semanal": str,           # "CRESCENDO" | "ESTAVEL" | "CAINDO"
        "mes_atual": float,
        "mes_anterior": float,
        "variacao_mensal_pct": float,
        "tendencia_mensal": str,
    }
    """
    agora = datetime.utcnow()
    
    def soma_periodo(inicio, fim):
        query = (
            db.query(func.sum(SalesOrderItem.quantity))
            .join(SalesOrder)
            .filter(
                SalesOrderItem.recipe_id == recipe_id,
                SalesOrder.status == "DELIVERED",
                SalesOrder.order_date >= inicio,
                SalesOrder.order_date < fim,
            )
        )
        if customer_id:
            query = query.filter(SalesOrder.customer_id == customer_id)
        return float(query.scalar() or 0)
    
    # Semanas
    semana_atual_inicio   = agora - timedelta(days=7)
    semana_anterior_inicio = agora - timedelta(days=14)
    
    sem_atual    = soma_periodo(semana_atual_inicio, agora)
    sem_anterior = soma_periodo(semana_anterior_inicio, semana_atual_inicio)
    
    # Meses
    mes_atual_inicio    = agora.replace(day=1)
    mes_anterior_inicio = (mes_atual_inicio - timedelta(days=1)).replace(day=1)
    
    mes_atual    = soma_periodo(mes_atual_inicio, agora)
    mes_anterior = soma_periodo(mes_anterior_inicio, mes_atual_inicio)
    
    def variacao(atual, anterior):
        if anterior == 0:
            return 100.0 if atual > 0 else 0.0
        return round(((atual - anterior) / anterior) * 100, 1)
    
    def tendencia(var_pct):
        if var_pct > 10:  return "CRESCENDO"
        if var_pct < -10: return "CAINDO"
        return "ESTAVEL"
    
    var_sem = variacao(sem_atual, sem_anterior)
    var_mes = variacao(mes_atual, mes_anterior)
    
    return {
        "semana_atual": sem_atual,
        "semana_anterior": sem_anterior,
        "variacao_semanal_pct": var_sem,
        "tendencia_semanal": tendencia(var_sem),
        "mes_atual": mes_atual,
        "mes_anterior": mes_anterior,
        "variacao_mensal_pct": var_mes,
        "tendencia_mensal": tendencia(var_mes),
    }
```

### 4.4 Função: `calcular_urgencia_producao(recipe_id, db)`

```python
def calcular_urgencia_producao(recipe_id: int, db: Session) -> dict:
    """
    Combina estoque atual com demanda média para calcular urgência de produção.
    
    Retorna:
    {
        "recipe_id": int,
        "estoque_atual": int,               # current_stock_units
        "media_diaria_30d": float,          # demanda média dos últimos 30 dias
        "dias_cobertura": float,            # estoque / media_diaria (dias restantes)
        "urgencia": str,                    # "CRITICO" | "ALERTA" | "OK" | "EXCESSO"
        "sugestao_producao": int,           # unidades sugeridas para produzir
        "sugestao_lotes": int,              # lotes (sugestao / rendimento_unidades)
        "producao_para_dias": int,          # para quantos dias sugerimos cobrir
        "justificativa": str,               # texto explicativo da sugestão
    }
    """
    recipe = db.query(Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        return {}
    
    demanda = calcular_demanda_produto(recipe_id, db, janela_dias=30)
    media_diaria = demanda["media_diaria"]
    estoque = recipe.current_stock_units or 0
    rendimento = max(1, recipe.rendimento_unidades or 1)
    
    # Dias de cobertura = estoque atual ÷ consumo médio diário
    dias_cobertura = (estoque / media_diaria) if media_diaria > 0 else 999
    
    # Classificação de urgência
    if media_diaria == 0:
        urgencia = "SEM_DEMANDA"
        sugestao = 0
        justificativa = "Sem histórico de vendas nos últimos 30 dias."
        producao_para_dias = 0
    elif dias_cobertura <= 1:
        urgencia = "CRITICO"
        producao_para_dias = 14  # cobrir 2 semanas
        sugestao = int(media_diaria * producao_para_dias)
        justificativa = (
            f"Estoque crítico! Cobertura de apenas {dias_cobertura:.1f} dia(s). "
            f"Produção imediata recomendada para {producao_para_dias} dias."
        )
    elif dias_cobertura <= 3:
        urgencia = "ALERTA"
        producao_para_dias = 14
        sugestao = int(media_diaria * producao_para_dias)
        justificativa = (
            f"Estoque baixo — cobertura de {dias_cobertura:.1f} dias. "
            f"Planejar produção para esta semana."
        )
    elif dias_cobertura <= 7:
        urgencia = "PLANEJAR"
        producao_para_dias = 14
        sugestao = int(media_diaria * producao_para_dias - estoque)
        justificativa = (
            f"Cobertura de {dias_cobertura:.1f} dias. "
            f"Incluir na produção desta semana."
        )
    elif dias_cobertura <= 21:
        urgencia = "OK"
        sugestao = 0
        producao_para_dias = 0
        justificativa = f"Estoque confortável — {dias_cobertura:.1f} dias de cobertura."
    else:
        urgencia = "EXCESSO"
        sugestao = 0
        producao_para_dias = 0
        justificativa = (
            f"Superprodução detectada — {dias_cobertura:.1f} dias de estoque. "
            f"Considere promoção ou redução de produção."
        )
    
    sugestao_lotes = (sugestao // rendimento) + (1 if sugestao % rendimento > 0 else 0)
    
    return {
        "recipe_id": recipe_id,
        "recipe_name": recipe.name,
        "estoque_atual": estoque,
        "media_diaria_30d": media_diaria,
        "dias_cobertura": round(dias_cobertura, 1),
        "urgencia": urgencia,
        "sugestao_producao": sugestao,
        "sugestao_lotes": sugestao_lotes,
        "producao_para_dias": producao_para_dias,
        "justificativa": justificativa,
    }
```

### 4.5 Função: `calcular_sugestao_pedido_cliente(recipe_id, customer_id, db)`

```python
def calcular_sugestao_pedido_cliente(
    recipe_id: int, 
    customer_id: int, 
    db: Session
) -> dict:
    """
    Calcula a sugestão de quantidade de pedido para um cliente específico,
    baseado no histórico de consumo dele para este produto.
    
    Retorna:
    {
        "recipe_id": int,
        "customer_id": int,
        "media_semanal_pacotes": float,     # média de pacotes pedidos por semana
        "ultimo_pedido_qtd": float,         # quantidade do último pedido
        "ultimo_pedido_data": date,         
        "dias_desde_ultimo_pedido": int,    
        "sugestao_pacotes": int,            # quantidade sugerida para este pedido
        "confianca": str,                   # "ALTA" | "MEDIA" | "BAIXA"
        "historico_pedidos": int,           # quantos pedidos há no histórico
        "mensagem": str,                    # texto amigável para o cliente
    }
    """
    desde_90d = datetime.utcnow() - timedelta(days=90)
    
    # Busca todos os pedidos entregues deste cliente para este produto
    itens = (
        db.query(SalesOrderItem)
        .join(SalesOrder)
        .filter(
            SalesOrderItem.recipe_id == recipe_id,
            SalesOrder.customer_id == customer_id,
            SalesOrder.status == "DELIVERED",
            SalesOrder.order_date >= desde_90d,
        )
        .order_by(SalesOrder.order_date.desc())
        .all()
    )
    
    if not itens:
        return {
            "recipe_id": recipe_id,
            "customer_id": customer_id,
            "sugestao_pacotes": 0,
            "confianca": "BAIXA",
            "historico_pedidos": 0,
            "mensagem": "Sem histórico de compra deste produto.",
        }
    
    # Quantidade total e média semanal
    total_qtd = sum(i.quantity for i in itens)
    media_semanal = total_qtd / 13  # 90 dias ≈ 13 semanas
    
    # Último pedido
    ultimo_item = itens[0]
    ultimo_data = ultimo_item.order.order_date.date()
    dias_desde = (datetime.utcnow().date() - ultimo_data).days
    
    # Sugestão: média semanal arredondada para cima, mínimo 1
    sugestao = max(1, round(media_semanal))
    
    # Ajuste: se faz muitos dias desde o último pedido, sugere um pouco mais
    if dias_desde > 14:
        sugestao = max(sugestao, round(media_semanal * 1.2))
    
    # Confiança baseada no volume de dados
    confianca = (
        "ALTA"  if len(itens) >= 5  else
        "MEDIA" if len(itens) >= 2  else
        "BAIXA"
    )
    
    # Mensagem amigável para exibir no portal do cliente
    if confianca == "ALTA":
        mensagem = (
            f"Baseado no seu histórico, você costuma pedir "
            f"em média {media_semanal:.1f} pacote(s) por semana."
        )
    elif confianca == "MEDIA":
        mensagem = (
            f"Com base nos seus últimos {len(itens)} pedidos, "
            f"sugerimos {sugestao} pacote(s)."
        )
    else:
        mensagem = "Pouco histórico disponível. A sugestão é baseada em 1 pedido."
    
    return {
        "recipe_id": recipe_id,
        "customer_id": customer_id,
        "media_semanal_pacotes": round(media_semanal, 2),
        "ultimo_pedido_qtd": ultimo_item.quantity,
        "ultimo_pedido_data": ultimo_data,
        "dias_desde_ultimo_pedido": dias_desde,
        "sugestao_pacotes": sugestao,
        "confianca": confianca,
        "historico_pedidos": len(itens),
        "mensagem": mensagem,
    }
```

### 4.6 Função: `serie_historica_cliente(customer_id, db, recipe_id=None, granularidade='semana')`

```python
def serie_historica_cliente(
    customer_id: int,
    db: Session,
    recipe_id: int = None,
    granularidade: str = "semana",   # "semana" | "mes"
    janela_semanas: int = 12
) -> list[dict]:
    """
    Retorna série temporal de consumo do cliente para alimentar os gráficos.
    
    Retorna lista de dicts:
    [
        {
            "periodo": "2026-01",          # Semana ISO ou Mês YYYY-MM
            "periodo_label": "Jan/2026",   # Label legível em PT-BR
            "quantidade": 12.0,            # Total de pacotes no período
            "valor_total": 456.80,         # Valor monetário total
            "num_pedidos": 2,              # Número de pedidos distintos
        },
        ...
    ]
    """
    desde = datetime.utcnow() - timedelta(weeks=janela_semanas)
    
    query = (
        db.query(SalesOrderItem, SalesOrder)
        .join(SalesOrder)
        .filter(
            SalesOrder.customer_id == customer_id,
            SalesOrder.status == "DELIVERED",
            SalesOrder.order_date >= desde,
        )
    )
    if recipe_id:
        query = query.filter(SalesOrderItem.recipe_id == recipe_id)
    
    resultados = query.all()
    
    # Agrega por semana ou mês
    agregado: dict[str, dict] = {}
    pedidos_por_periodo: dict[str, set] = {}
    
    for item, order in resultados:
        if granularidade == "mes":
            chave = order.order_date.strftime("%Y-%m")
            label = order.order_date.strftime("%b/%Y").capitalize()
        else:
            chave = order.order_date.strftime("%Y-W%W")
            # Label "Sem X/YYYY"
            semana_num = order.order_date.isocalendar()[1]
            label = f"Sem {semana_num}/{order.order_date.year}"
        
        if chave not in agregado:
            agregado[chave] = {
                "periodo": chave,
                "periodo_label": label,
                "quantidade": 0.0,
                "valor_total": 0.0,
                "num_pedidos": 0,
            }
            pedidos_por_periodo[chave] = set()
        
        agregado[chave]["quantidade"]   += item.quantity
        agregado[chave]["valor_total"]  += item.quantity * item.unit_price
        pedidos_por_periodo[chave].add(order.id)
    
    # Atualiza contagem de pedidos únicos
    for chave in agregado:
        agregado[chave]["num_pedidos"] = len(pedidos_por_periodo[chave])
        agregado[chave]["valor_total"] = round(agregado[chave]["valor_total"], 2)
    
    return sorted(agregado.values(), key=lambda x: x["periodo"])
```

### 4.7 Função: `gerar_plano_producao_semanal(db)`

```python
def gerar_plano_producao_semanal(db: Session) -> list[dict]:
    """
    Itera sobre todos os produtos com estoque registrado e gera
    a lista priorizada de produção para a semana atual.
    
    Retorna lista ordenada por urgência (CRITICO primeiro):
    [
        {
            "recipe_id": int,
            "recipe_name": str,
            "urgencia": str,
            "urgencia_ordem": int,       # para ordenação: 1=CRITICO, 2=ALERTA, ...
            "estoque_atual": int,
            "dias_cobertura": float,
            "media_semanal": float,
            "sugestao_producao": int,
            "sugestao_lotes": int,
            "justificativa": str,
            "crescimento_pct": float,    # crescimento vs. semana anterior
            "tendencia": str,
        },
        ...
    ]
    """
    ORDEM_URGENCIA = {
        "CRITICO": 1, "ALERTA": 2, "PLANEJAR": 3,
        "OK": 4, "EXCESSO": 5, "SEM_DEMANDA": 6
    }
    
    recipes = db.query(Recipe).all()
    plano = []
    
    for recipe in recipes:
        urgencia = calcular_urgencia_producao(recipe.id, db)
        if urgencia.get("urgencia") in ("OK", "EXCESSO", "SEM_DEMANDA"):
            # Inclui na lista mas com baixa prioridade
            pass
        
        crescimento = calcular_taxa_crescimento(recipe.id, db)
        
        plano.append({
            **urgencia,
            "urgencia_ordem": ORDEM_URGENCIA.get(urgencia.get("urgencia", "OK"), 4),
            "media_semanal": urgencia.get("media_diaria_30d", 0) * 7,
            "crescimento_pct": crescimento.get("variacao_semanal_pct", 0),
            "tendencia": crescimento.get("tendencia_semanal", "ESTAVEL"),
        })
    
    return sorted(plano, key=lambda x: (x["urgencia_ordem"], -x.get("media_semanal", 0)))
```

---

## 5. Etapa D — Painel de Inteligência de Produção

### 5.1 Objetivo

Dar ao time de produção uma tela de decisão única que responde: **"O que produzir agora? Quanto? Por quê?"**

### 5.2 URL e Acesso

```
GET /inteligencia
Acesso: ADMIN e PRODUCAO
Sidebar: nova entrada "🧠 Inteligência" na seção "Fábrica"
```

### 5.3 Layout Completo da Tela

```
╔══════════════════════════════════════════════════════════════════════╗
║  🧠 Inteligência de Produção          Atualizado: há 3min [↻]       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  KPIs RÁPIDOS                                                        ║
║  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────────┐ ║
║  │ 2            │ │ 1            │ │ R$ 3.840     │ │ ↑ +12%     │ ║
║  │ Produzir hoje│ │ Alerta       │ │ Demanda/sem. │ │ Crescimento │ ║
║  └──────────────┘ └──────────────┘ └──────────────┘ └────────────┘ ║
║                                                                      ║
║  ─────────────────────────────────────────────────────────────────  ║
║  FILA DE PRODUÇÃO — Ordenada por Urgência                            ║
║                                                                      ║
║  🚨 CRÍTICO — Produzir HOJE                                          ║
║                                                                      ║
║  ┌─────────────────────────────────────────────────────────────┐   ║
║  │  Coxinha de Frango                          [▶ Produzir]   │   ║
║  │  ────────────────────────────────────────                   │   ║
║  │  Estoque: 40 un.    Cobertura: 0,8 dias                     │   ║
║  │  Demanda: 48 un/sem  (↑ +18% vs. sem. ant.)                 │   ║
║  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 8% ████▌        │   ║
║  │                                                             │   ║
║  │  💡 Produzir agora: 320 unidades (6 lotes)                  │   ║
║  │     Para cobrir os próximos 14 dias de demanda.             │   ║
║  └─────────────────────────────────────────────────────────────┘   ║
║                                                                      ║
║  ⚠️ ALERTA — Planejar esta semana                                    ║
║                                                                      ║
║  ┌─────────────────────────────────────────────────────────────┐   ║
║  │  Bolinha de Queijo                          [▶ Produzir]   │   ║
║  │  Estoque: 55 un.    Cobertura: 2,5 dias                     │   ║
║  │  Demanda: 22 un/sem  (→ Estável)                            │   ║
║  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 25% ████████▌   │   ║
║  │  💡 Produzir: 154 unidades (4 lotes) esta semana.           │   ║
║  └─────────────────────────────────────────────────────────────┘   ║
║                                                                      ║
║  📅 PLANEJAR — Incluir no planejamento                              ║
║  [ver mais 3 produtos ▼]                                             ║
║                                                                      ║
║  ✅ OK — Estoque confortável                                         ║
║  [ver 2 produtos ▼]                                                  ║
║                                                                      ║
║  ─────────────────────────────────────────────────────────────────  ║
║  TENDÊNCIAS POR PRODUTO — Últimas 12 semanas                        ║
║                                                                      ║
║  [Coxinha de Frango ▼]                                              ║
║                                                                      ║
║  Semanas →                                                           ║
║  60 ┤                                          ●                     ║
║  50 ┤                             ●        ●       ←  pico           ║
║  40 ┤                  ●    ●                                        ║
║  30 ┤         ●                                                      ║
║  20 ┤    ●                                                           ║
║   0 └────────────────────────────────────────────────────────       ║
║        Jan   Fev   Mar   Abr   Mai                                   ║
║                                                                      ║
║  Média: 38 un/sem   Pico: 58   Mínimo: 18   Tendência: ↑ Crescendo  ║
╚══════════════════════════════════════════════════════════════════════╝
```

### 5.4 Cards de Urgência — Especificação Visual

**CRÍTICO (vermelho — border-left: 4px solid #dc2626)**
- Badge: "🚨 CRÍTICO"
- Dias de cobertura em vermelho, grande
- Barra de progresso de estoque (0–100% da meta de 14 dias) — quase vazia
- Botão primário [▶ Produzir agora] — leva para /producao com a receita pré-selecionada
- Texto sugestão em destaque: "Produzir X unidades (Y lotes)"

**ALERTA (âmbar — border-left: 4px solid #d97706)**
- Badge: "⚠️ ALERTA"
- Mesma estrutura, cores âmbar

**PLANEJAR (azul — border-left: 4px solid #2563eb)**
- Badge: "📅 PLANEJAR"
- Sem urgência visual, mas incluso no plano da semana
- Pode ser colapsado por padrão

**OK (verde — border-left: 4px solid #16a34a)**
- Badge: "✅ OK"
- Apenas lista, sem destaque
- Colapsado por padrão com "ver N produtos"

**EXCESSO (cinza — border-left: 4px solid #6b7280)**
- Badge: "📦 EXCESSO"
- Alerta de superprodução: "Avalie promoção para girar o estoque"

### 5.5 Seção de Tendências — Gráfico SVG Inline

O gráfico de tendência por produto é gerado em **SVG puro pelo backend Python** e injetado no HTML. Não usa Chart.js nem qualquer biblioteca externa — apenas cálculo de coordenadas e tags SVG.

```python
def gerar_grafico_svg(serie: list[dict], largura=500, altura=160) -> str:
    """
    Gera um SVG simples de linha para a série histórica.
    Retorna string HTML/SVG segura para injeção via | safe no Jinja2.
    """
    if not serie:
        return "<p>Sem dados suficientes para gerar gráfico.</p>"
    
    valores = [s["quantidade"] for s in serie]
    labels  = [s["periodo_label"] for s in serie]
    n = len(valores)
    
    max_val = max(valores) if valores else 1
    min_val = min(valores)
    
    pad_x, pad_y = 40, 20
    w = largura - pad_x * 2
    h = altura  - pad_y * 2
    
    def cx(i):  return pad_x + (i / max(n - 1, 1)) * w
    def cy(v):  return pad_y + h - ((v - min_val) / max(max_val - min_val, 1)) * h
    
    pontos_poly = " ".join(f"{cx(i):.1f},{cy(v):.1f}" for i, v in enumerate(valores))
    pontos_area = f"{cx(0):.1f},{pad_y + h} {pontos_poly} {cx(n-1):.1f},{pad_y + h}"
    
    # Pontos individuais
    circles = "".join(
        f'<circle cx="{cx(i):.1f}" cy="{cy(v):.1f}" r="3" fill="#2563eb"/>'
        for i, v in enumerate(valores)
    )
    
    # Labels do eixo X (apenas primeiro, meio e último)
    idx_labels = [0, n // 2, n - 1] if n > 2 else list(range(n))
    eixo_x = "".join(
        f'<text x="{cx(i):.1f}" y="{altura - 4}" text-anchor="middle" '
        f'font-size="9" fill="#94a3b8">{labels[i]}</text>'
        for i in idx_labels if i < n
    )
    
    return f"""
    <svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}"
         xmlns="http://www.w3.org/2000/svg" style="overflow:visible">
      <defs>
        <linearGradient id="area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#2563eb" stop-opacity="0.15"/>
          <stop offset="100%" stop-color="#2563eb" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="{pontos_area}" fill="url(#area-grad)"/>
      <polyline points="{pontos_poly}" fill="none" stroke="#2563eb" stroke-width="1.5" stroke-linejoin="round"/>
      {circles}
      {eixo_x}
    </svg>
    """
```

### 5.6 Botão "Produzir" — Integração com /producao

O botão [▶ Produzir] em cada card direciona para `/producao?recipe_id={id}`, e o módulo de produção existente lê o parâmetro e pré-seleciona a receita automaticamente.

**Alteração necessária em `templates/producao.html`:**
```javascript
// No kdsApp.init():
const params = new URLSearchParams(window.location.search);
const preselect = params.get('recipe_id');
if (preselect) {
  this.selectedId = parseInt(preselect);
  this.loadRecipe();
}
```

### 5.7 Rotas Backend — Etapa D

| Método | URL | Função |
|---|---|---|
| GET | `/inteligencia` | Página principal do painel |
| GET | `/api/inteligencia/plano` | JSON com plano de produção atual |
| GET | `/api/inteligencia/tendencia/{recipe_id}` | JSON com série histórica de um produto |
| GET | `/api/inteligencia/grafico/{recipe_id}` | HTML com SVG do gráfico (HTMX) |

### 5.8 Arquivos — Etapa D

| Arquivo | Natureza |
|---|---|
| `intelligence_engine.py` | Novo — motor de cálculo (Python puro) |
| `main.py` | Adicionar rotas /inteligencia e /api/inteligencia/* |
| `templates/inteligencia.html` | Novo — dashboard de produção |
| `templates/base.html` | Adicionar link "🧠 Inteligência" na sidebar (seção Fábrica) |

---

## 6. Etapa E — Análise de Consumo para o Cliente

### 6.1 Objetivo

Dar ao cliente do portal (bar/restaurante) uma visão clara do próprio histórico de compras: quanto consome por semana/mês, se está comprando mais ou menos, e qual produto lidera o consumo.

### 6.2 URL e Acesso

```
GET /loja/consumo
Acesso: usuário tipo CLIENTE (sessão com cliente_id)
Navegação: link "📊 Meu Consumo" no menu do portal
```

### 6.3 Layout Completo da Tela

```
╔══════════════════════════════════════════════════════════════════════╗
║  📊 Meu Consumo — Boteco do Zé                                       ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  KPIs DO MÊS ATUAL                                                   ║
║  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐           ║
║  │  18 pacotes    │ │  R$ 847,20     │ │  ↑ +22%        │           ║
║  │  Comprados     │ │  Gasto total   │ │  vs. mês ant.  │           ║
║  └────────────────┘ └────────────────┘ └────────────────┘           ║
║                                                                      ║
║  CONSUMO POR PERÍODO                                                 ║
║  [Semanal ●] [Mensal ○]       Ver: [Todos os produtos ▼]            ║
║                                                                      ║
║  Qtd. ┤                                                              ║
║    8  ┤              ██                  ██                          ║
║    6  ┤    ██    ██  ██  ██    ██    ██  ██  ██                     ║
║    4  ┤    ██    ██  ██  ██    ██    ██  ██  ██                     ║
║    2  ┤    ██    ██  ██  ██    ██    ██  ██  ██                     ║
║    0  └──────────────────────────────────────────────────           ║
║         S1  S2  S3  S4  S5  S6  S7  S8  S9  S10  S11  S12          ║
║         ← 12 semanas                                                 ║
║                                                                      ║
║  TENDÊNCIA  ↑ Crescendo — seus pedidos aumentaram 22% no mês        ║
║                                                                      ║
║  ─────────────────────────────────────────────────────────────────  ║
║  CONSUMO POR PRODUTO                                                 ║
║                                                                      ║
║  🍗 Coxinha de Frango                                               ║
║  ████████████████████████████░░░░░░░░  62% do consumo               ║
║  Média: 2,1 pct/semana   ↑ +18% vs. mês anterior                   ║
║  Último pedido: há 5 dias (3 pacotes)                               ║
║  ┌────────────────────────────────────┐                             ║
║  │  Próximo pedido sugerido: 3 pct   │  [Pedir agora →]            ║
║  └────────────────────────────────────┘                             ║
║                                                                      ║
║  🧀 Bolinha de Queijo                                               ║
║  ███████████████░░░░░░░░░░░░░░░░░░░░  28% do consumo               ║
║  Média: 0,9 pct/semana   → Estável                                  ║
║  Último pedido: há 12 dias (1 pacote)                               ║
║  ┌────────────────────────────────────┐                             ║
║  │  Próximo pedido sugerido: 1 pct   │  [Pedir agora →]            ║
║  └────────────────────────────────────┘                             ║
║                                                                      ║
║  🌮 Kibe Frito                                                       ║
║  ████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  10% do consumo               ║
║  Média: 0,3 pct/semana   ↓ -5% vs. mês anterior                    ║
║  Último pedido: há 22 dias (1 pacote)                               ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

### 6.4 Componentes da Tela — Detalhamento

#### KPI Cards

| KPI | Cálculo | Cor |
|---|---|---|
| Total de pacotes no mês | Soma de `quantity` em pedidos DELIVERED do mês corrente | Azul |
| Gasto total no mês | Soma de `quantity * unit_price` dos pedidos do mês | Verde |
| Variação vs. mês anterior | `(mes_atual - mes_anterior) / mes_anterior * 100` | Verde se ↑, Vermelho se ↓ |

#### Gráfico de Barras de Consumo

- Toggle: **Semanal** (12 semanas) ou **Mensal** (12 meses)
- Filtro: "Todos os produtos" ou produto específico via dropdown
- Barras simples em HTML+CSS (sem biblioteca externa): `div` com altura proporcional ao valor
- Eixo X: labels de semana/mês
- Tooltip simples em Alpine.js ao hover

#### Seção por Produto

Para cada produto comprado pelo cliente (no histórico de 90 dias):
- Percentual de participação no consumo total (barra visual)
- Média semanal de pacotes
- Indicador de tendência (↑ ↓ →)
- Dias desde o último pedido
- Caixa de sugestão com botão "Pedir agora"

#### Indicador de Tendência

| Variação Semanal | Ícone | Texto |
|---|---|---|
| > +10% | ↑ verde | "Crescendo" |
| -10% a +10% | → cinza | "Estável" |
| < -10% | ↓ vermelho | "Caindo" |

### 6.5 Insight de Alerta — "Você não pede há X dias"

Se o cliente está há mais de 10 dias sem pedir um produto que costumava comprar semanalmente, a tela exibe um alerta contextual:

```
┌──────────────────────────────────────────────────────────────┐
│  ⏰  Você não pede Bolinha de Queijo há 12 dias.             │
│      Com base no seu histórico, você costuma pedir           │
│      a cada 7 dias. Está faltando em estoque?               │
│                                                              │
│      [Pedir agora — 1 pacote sugerido →]                    │
└──────────────────────────────────────────────────────────────┘
```

### 6.6 Rotas Backend — Etapa E

| Método | URL | Função |
|---|---|---|
| GET | `/loja/consumo` | Página de análise de consumo do cliente |
| GET | `/api/loja/consumo/serie` | JSON com série histórica (para gráfico via HTMX) |
| GET | `/api/loja/consumo/produtos` | JSON com consumo detalhado por produto |

---

## 7. Etapa F — Sugestão de Pedido Inteligente no Portal

### 7.1 Objetivo

Integrar as sugestões diretamente no catálogo de compras `/loja`, sem precisar que o cliente navegue para /loja/consumo. A sugestão aparece como um **campo pré-preenchido sugerido** no card de cada produto.

### 7.2 Integração no Card de Produto

O card de produto existente (Etapa B do v3.0) ganha uma linha adicional com a sugestão:

```
┌──────────────────────────────────┐
│  📸  Coxinha Artesanal de Frango │
│       pct 50 un. · R$ 47,90     │
│                                  │
│  ─────────────────────────────   │
│  💡 Sugestão: 3 pacotes          │
│     Seu consumo médio: 2,8/sem   │
│  ─────────────────────────────   │
│                                  │
│  [ − ] [ 3 ] [ + ]    🛒         │
│          ↑                       │
│    pré-preenchido                │
└──────────────────────────────────┘
```

**Comportamento:**
- A quantidade no seletor começa em `sugestao_pacotes` (da função `calcular_sugestao_pedido_cliente`), não em 0.
- Se o cliente alterar a quantidade manualmente, a sugestão não interfere mais.
- Badge de confiança visível: "💡 Sugestão" (confiança ALTA), "• Sugestão" (confiança MEDIA/BAIXA).

### 7.3 Carrinho Inteligente — Revisão com Insights

Na tela do carrinho `/loja/carrinho`, cada item mostra um insight adicional:

```
┌──────────────────────────────────────────────────────────────┐
│  Coxinha de Frango    3 pct × R$ 47,90 = R$ 143,70         │
│                                                              │
│  ℹ️  Você pediu 2 pct no último pedido (há 8 dias).          │
│      Médio: 2,8 pct/semana. Pedido de 3 pct está adequado. │
└──────────────────────────────────────────────────────────────┘
```

### 7.4 Banner "Você pode estar precisando"

Na parte superior do catálogo `/loja`, se detectado que o cliente está próximo do ponto de reposição de algum produto, aparece um banner contextual (não intrusivo):

```
┌─────────────────────────────────────────────────────────────┐
│  🔔  Com base no seu histórico, você costuma pedir Bolinha   │
│      de Queijo a cada 7 dias. Seu último pedido foi há 9   │
│      dias. Está no carrinho?                                │
│                              [Adicionar 1 pacote →]  [×]   │
└─────────────────────────────────────────────────────────────┘
```

**Regra de disparo:** Apenas um produto por vez (o de maior urgência para o cliente). Fecha-se ao clicar × e não reaparece na mesma sessão.

### 7.5 Rotas Backend — Etapa F

| Método | URL | Função |
|---|---|---|
| GET | `/api/loja/sugestoes` | JSON com sugestões de pedido para o cliente logado |
| GET | `/api/loja/alertas` | JSON com alertas de reposição para o cliente logado |

Esses endpoints são chamados via `fetch()` no carregamento de `/loja` e injetam os dados nos cards via Alpine.js.

---

## 8. Requisitos de Design

### 8.1 Painel de Inteligência (/inteligencia) — Design ERP

Extensão do design system existente (`base.html`). Não cria novo layout.

| Elemento | Especificação |
|---|---|
| Cards de urgência | Border-left 4px colorida por urgência. Sem background colorido (mantém --card). |
| Barra de estoque | `div` com `width: X%` em CSS, colorida conforme urgência |
| Indicador de tendência | ↑ verde (#16a34a), → cinza (#6b7280), ↓ vermelho (#dc2626) |
| Gráfico SVG | Gerado no backend, injetado via Jinja2. Linha azul (#2563eb), área com alpha 15% |
| Botão "Produzir" | `btn btn-primary btn-sm` com link para /producao?recipe_id=X |
| Seções colapsáveis | `<details>/<summary>` HTML nativo. OK e EXCESSO colapsados por padrão |

### 8.2 Análise de Consumo (/loja/consumo) — Design Portal Cliente

Usa o layout do portal (`base_loja.html` criado no v3.0). Mesmas cores e fontes.

| Elemento | Especificação |
|---|---|
| Gráfico de barras | Barras em HTML puro: `divs` com `height` proporcional em % do máximo. Cor: #16a34a |
| Toggle Semanal/Mensal | Segmented control (mesma classe `.seg-ctrl` do ERP) |
| Barra de participação por produto | `div` com `width: X%`, cor por produto (azul, verde, âmbar, roxo, vermelho) |
| KPI cards | Mesmos `.card` com `.kpi-green`, `.kpi-blue` do ERP |
| Insight de alerta | Card amarelo com `border-left: 4px solid #f59e0b` |
| Ícones de tendência | ↑ 🟢 ↓ 🔴 → ⚪ (com texto ao lado, nunca ícone isolado) |
| Botão "Pedir agora" | Leva para `/loja?produto={id}` com scroll automático para o card |

### 8.3 Sugestão no Card de Produto — Design Portal

| Elemento | Especificação |
|---|---|
| Linha de sugestão | `text-xs`, cor `var(--muted)`, ícone 💡 apenas em alta confiança |
| Quantidade pré-preenchida | Campo numérico com valor = `sugestao_pacotes`, editável normalmente |
| Badge de confiança | Sem badge se BAIXA. "💡" se ALTA. "•" se MEDIA. |

### 8.4 Performance

| Requisito | Meta |
|---|---|
| /inteligencia — carregamento inicial | < 2 segundos (cálculo pesado, aceita um pouco mais) |
| /loja/consumo — carregamento inicial | < 1,5 segundos |
| /loja — sugestões (fetch assíncrono) | < 500ms (carregado após o catálogo) |
| Gráfico SVG (gerado no backend) | < 100ms |

---

## 9. Especificação Técnica Completa

### 9.1 Estrutura de Arquivos

```
smartfood/
├── intelligence_engine.py          ← NOVO — motor de cálculo
├── main.py                         ← adicionar rotas D, E, F
├── templates/
│   ├── inteligencia.html           ← NOVO — painel de produção
│   └── loja/
│       ├── consumo.html            ← NOVO — análise do cliente
│       └── catalogo.html           ← MODIFICAR — adicionar sugestões
```

### 9.2 Rotas Completas — Módulo de Inteligência

```python
# ── Etapa D: Painel de Produção ───────────────────────────────────────

@app.get("/inteligencia", response_class=HTMLResponse)
async def inteligencia_page(request: Request, db: Session = Depends(get_db)):
    """Painel de inteligência de produção — apenas ADMIN e PRODUCAO."""
    require_admin(request)   # dependency
    
    from intelligence_engine import gerar_plano_producao_semanal
    plano = gerar_plano_producao_semanal(db)
    
    criticos  = [p for p in plano if p["urgencia"] == "CRITICO"]
    alertas   = [p for p in plano if p["urgencia"] == "ALERTA"]
    planejar  = [p for p in plano if p["urgencia"] == "PLANEJAR"]
    ok        = [p for p in plano if p["urgencia"] == "OK"]
    excesso   = [p for p in plano if p["urgencia"] == "EXCESSO"]
    
    # KPIs resumidos
    demanda_semana_rs = sum(
        p["media_semanal"] * _preco_venda(p["recipe_id"], db)
        for p in plano if p.get("media_semanal", 0) > 0
    )
    
    return templates.TemplateResponse("inteligencia.html", {
        "request": request,
        "active_page": "inteligencia",
        "criticos": criticos,
        "alertas": alertas,
        "planejar": planejar,
        "ok": ok,
        "excesso": excesso,
        "total_criticos": len(criticos),
        "total_alertas": len(alertas),
        "demanda_semana_rs": demanda_semana_rs,
        "recipes": db.query(models.Recipe).order_by(models.Recipe.name).all(),
    })


@app.get("/api/inteligencia/grafico/{recipe_id}", response_class=HTMLResponse)
async def inteligencia_grafico(
    recipe_id: int,
    request: Request,
    janela: int = 12,       # semanas
    db: Session = Depends(get_db),
):
    """Retorna SVG do gráfico de tendência para HTMX injection."""
    from intelligence_engine import serie_historica_cliente, gerar_grafico_svg
    
    # Para o painel de produção, agrega TODOS os clientes
    serie = serie_historica_cliente(
        customer_id=None,  # None = todos os clientes
        db=db,
        recipe_id=recipe_id,
        granularidade="semana",
        janela_semanas=janela,
    )
    svg = gerar_grafico_svg(serie)
    return HTMLResponse(content=svg)


# ── Etapa E: Consumo do Cliente ───────────────────────────────────────

@app.get("/loja/consumo", response_class=HTMLResponse)
async def loja_consumo_page(request: Request, db: Session = Depends(get_db)):
    """Análise de consumo do cliente logado."""
    customer = get_current_customer(request, db)   # dependency
    
    from intelligence_engine import (
        serie_historica_cliente, calcular_taxa_crescimento,
        calcular_sugestao_pedido_cliente
    )
    
    # KPIs do mês
    serie_mensal = serie_historica_cliente(
        customer.id, db, granularidade="mes", janela_semanas=52
    )
    mes_atual    = serie_mensal[-1]["quantidade"] if serie_mensal else 0
    mes_anterior = serie_mensal[-2]["quantidade"] if len(serie_mensal) >= 2 else 0
    gasto_mes    = serie_mensal[-1]["valor_total"] if serie_mensal else 0
    variacao_mes = round(
        ((mes_atual - mes_anterior) / mes_anterior * 100) if mes_anterior else 0, 1
    )
    
    # Série semanal (para gráfico)
    serie_semanal = serie_historica_cliente(
        customer.id, db, granularidade="semana", janela_semanas=12
    )
    
    # Consumo por produto
    produtos_consumidos = _produtos_do_cliente(customer.id, db)
    produtos_detalhes = []
    total_qtd = sum(p["quantidade_total"] for p in produtos_consumidos)
    
    for p in produtos_consumidos:
        crescimento = calcular_taxa_crescimento(p["recipe_id"], db, customer.id)
        sugestao    = calcular_sugestao_pedido_cliente(p["recipe_id"], customer.id, db)
        produtos_detalhes.append({
            **p,
            "participacao_pct": round(p["quantidade_total"] / total_qtd * 100) if total_qtd else 0,
            **crescimento,
            "sugestao": sugestao,
        })
    
    return templates.TemplateResponse("loja/consumo.html", {
        "request": request,
        "active_page": "consumo",
        "customer": customer,
        "mes_atual_qtd": mes_atual,
        "mes_anterior_qtd": mes_anterior,
        "variacao_mensal_pct": variacao_mes,
        "gasto_mes": gasto_mes,
        "serie_semanal_json": serie_semanal,
        "serie_mensal_json": serie_mensal,
        "produtos": produtos_detalhes,
    })


# ── Etapa F: Sugestões no Catálogo ───────────────────────────────────

@app.get("/api/loja/sugestoes", response_class=JSONResponse)
async def api_loja_sugestoes(request: Request, db: Session = Depends(get_db)):
    """Retorna sugestões de pedido para todos os produtos do cliente logado."""
    customer = get_current_customer(request, db)
    
    from intelligence_engine import calcular_sugestao_pedido_cliente
    
    recipes = db.query(models.Recipe).filter_by(visivel_loja=1).all()
    sugestoes = {}
    for recipe in recipes:
        sug = calcular_sugestao_pedido_cliente(recipe.id, customer.id, db)
        if sug.get("sugestao_pacotes", 0) > 0:
            sugestoes[recipe.id] = sug
    
    return JSONResponse(sugestoes)
```

### 9.3 Função Auxiliar — Produtos do Cliente

```python
def _produtos_do_cliente(customer_id: int, db: Session) -> list[dict]:
    """
    Lista todos os produtos que o cliente comprou nos últimos 90 dias,
    com quantidade total e informações da receita.
    """
    desde = datetime.utcnow() - timedelta(days=90)
    
    rows = (
        db.query(
            SalesOrderItem.recipe_id,
            Recipe.name.label("recipe_name"),
            func.sum(SalesOrderItem.quantity).label("quantidade_total"),
            func.max(SalesOrder.order_date).label("ultimo_pedido"),
            func.count(SalesOrder.id.distinct()).label("num_pedidos"),
        )
        .join(SalesOrder)
        .join(Recipe, Recipe.id == SalesOrderItem.recipe_id)
        .filter(
            SalesOrder.customer_id == customer_id,
            SalesOrder.status == "DELIVERED",
            SalesOrder.order_date >= desde,
        )
        .group_by(SalesOrderItem.recipe_id)
        .order_by(func.sum(SalesOrderItem.quantity).desc())
        .all()
    )
    
    return [
        {
            "recipe_id": r.recipe_id,
            "recipe_name": r.recipe_name,
            "quantidade_total": float(r.quantidade_total or 0),
            "ultimo_pedido": r.ultimo_pedido,
            "dias_desde_ultimo": (datetime.utcnow() - r.ultimo_pedido).days if r.ultimo_pedido else 999,
            "num_pedidos": r.num_pedidos,
        }
        for r in rows
    ]
```

### 9.4 Ajuste em `serie_historica_cliente` para Suporte ao Painel de Produção

A função aceita `customer_id=None` para agregar todos os clientes (uso no painel de produção):

```python
def serie_historica_cliente(customer_id, db, recipe_id=None, ...):
    query = db.query(...)...
    if customer_id is not None:   # None = todos os clientes
        query = query.filter(SalesOrder.customer_id == customer_id)
    ...
```

### 9.5 Impacto em `main.py` — Imports Necessários

```python
from sqlalchemy import func
import intelligence_engine as ie
```

### 9.6 Considerações de Performance — Cache Simples

O painel de inteligência (`/inteligencia`) agrega todos os produtos e faz múltiplas queries. Para evitar lentidão, um cache em memória com TTL de 5 minutos é suficiente:

```python
import time
_intelligence_cache: dict = {}
CACHE_TTL = 300  # 5 minutos

def get_plano_cached(db: Session) -> list[dict]:
    agora = time.time()
    if "plano" in _intelligence_cache:
        dados, ts = _intelligence_cache["plano"]
        if agora - ts < CACHE_TTL:
            return dados
    plano = gerar_plano_producao_semanal(db)
    _intelligence_cache["plano"] = (plano, agora)
    return plano
```

Cache invalidado automaticamente quando um novo pedido é criado (via `POST /orders`).

---

## 10. Critérios de Aceite

### Etapa D — Painel de Inteligência de Produção

| # | Cenário | Resultado Esperado |
|---|---|---|
| D1 | Produto com estoque < 1 dia de cobertura | Aparece como CRÍTICO no topo da fila |
| D2 | Produto com estoque entre 1–3 dias | Aparece como ALERTA |
| D3 | Produto com estoque entre 3–7 dias | Aparece como PLANEJAR |
| D4 | Produto com estoque > 7 dias | Aparece como OK (colapsado por padrão) |
| D5 | Produto com demanda crescendo > 10% | Indicador ↑ verde na linha do produto |
| D6 | Produto com demanda caindo > 10% | Indicador ↓ vermelho |
| D7 | Clicar "Produzir" em card CRÍTICO | Redireciona para /producao com receita pré-selecionada |
| D8 | Produto sem nenhum pedido nos 30 dias | Status SEM_DEMANDA, sem sugestão de produção |
| D9 | Produto com excesso de estoque (> 21 dias) | Status EXCESSO, alerta de superprodução |
| D10 | Gráfico de tendência | Exibe 12 semanas corretamente, sem erros de divisão por zero |
| D11 | Acesso sem sessão ADMIN/PRODUCAO | HTTP 403 |
| D12 | Sugestão de produção calculada | Quantidade = media_diaria × 14 - estoque_atual, mínimo 0 |

### Etapa E — Análise de Consumo do Cliente

| # | Cenário | Resultado Esperado |
|---|---|---|
| E1 | Cliente sem nenhum pedido no histórico | KPIs mostram 0, lista de produtos vazia, mensagem amigável |
| E2 | Cliente com pedidos em 2 períodos distintos | Variação calculada corretamente |
| E3 | Produto com crescimento > 10% semanal | Badge ↑ verde |
| E4 | Toggle Semanal → Mensal | Gráfico re-renderiza sem reload da página |
| E5 | Filtro por produto específico | Gráfico mostra apenas série do produto selecionado |
| E6 | Produto não pedido há > 10 dias (padrão semanal) | Banner de alerta exibido |
| E7 | Cliente acessa dados de OUTRO cliente via URL manipulation | HTTP 403 — isolamento garantido |
| E8 | Botão "Pedir agora" no produto | Redireciona para /loja com foco no card do produto |
| E9 | Barra de participação | Soma das participações = 100% |
| E10 | KPI gasto do mês | Valor correto em R$ com 2 casas decimais |

### Etapa F — Sugestão Inteligente no Catálogo

| # | Cenário | Resultado Esperado |
|---|---|---|
| F1 | Produto com 5+ pedidos históricos | Campo quantidade pré-preenchido com sugestão, badge 💡 |
| F2 | Produto com 1–2 pedidos | Campo pré-preenchido, badge sem 💡 (confiança MEDIA) |
| F3 | Produto sem histórico | Campo pré-preenchido com 0, sem badge de sugestão |
| F4 | Cliente altera quantidade sugerida | Alteração persiste normalmente, sem interferência |
| F5 | Banner de alerta de reposição | Exibe apenas 1 produto por vez (o mais urgente) |
| F6 | Fechar banner × | Não reaparece na mesma sessão (Alpine.js state) |
| F7 | /api/loja/sugestoes responde | < 500ms |
| F8 | Insight no carrinho | Exibe comparação com último pedido para cada item |

---

## 11. Plano de Implementação

### Semana 4 — Etapa D (Painel de Produção)

```
Dia 1:  Criar intelligence_engine.py com funções:
        - calcular_demanda_produto()
        - calcular_taxa_crescimento()
        - calcular_urgencia_producao()
        - gerar_plano_producao_semanal()
        Testar funções isoladas com dados reais do banco

Dia 2:  Criar rota GET /inteligencia em main.py
        Criar templates/inteligencia.html (estrutura básica)
        Implementar cards CRÍTICO e ALERTA

Dia 3:  Implementar cards PLANEJAR, OK, EXCESSO
        Adicionar seções colapsáveis com <details>/<summary>
        Implementar KPI cards no topo

Dia 4:  Implementar gerar_grafico_svg() no engine
        Adicionar rota GET /api/inteligencia/grafico/{id}
        Integrar gráfico com HTMX no template
        Adicionar botão "Produzir" com redirect para /producao?recipe_id

Dia 5:  Adicionar link "🧠 Inteligência" na sidebar (base.html)
        Adicionar cache simples (5min) para o plano
        Testar critérios D1–D12
        Ajustes e documentação
```

### Semana 5 — Etapas E e F (Portal do Cliente)

```
Dia 1:  Adicionar funções ao intelligence_engine.py:
        - calcular_sugestao_pedido_cliente()
        - serie_historica_cliente()
        - _produtos_do_cliente()
        Testar com dados de clientes reais

Dia 2:  Criar rota GET /loja/consumo
        Criar templates/loja/consumo.html
        Implementar KPI cards e lista de produtos

Dia 3:  Implementar gráfico de barras em HTML puro (sem Chart.js)
        Implementar toggle Semanal/Mensal com Alpine.js
        Implementar filtro por produto

Dia 4:  Criar rota GET /api/loja/sugestoes
        Modificar templates/loja/catalogo.html para exibir sugestões
        Implementar banner de alerta de reposição

Dia 5:  Adicionar insights no carrinho (loja/carrinho.html)
        Testar critérios E1–E10 e F1–F8
        Ajustes de performance
        Documentação final
```

### Rollback

- **Etapa D:** Remover rota `/inteligencia` e arquivo `intelligence_engine.py`. Zero impacto no restante do sistema.
- **Etapa E:** Remover rota `/loja/consumo`. Zero impacto no catálogo.
- **Etapa F:** Remover fetch de `/api/loja/sugestoes` do `catalogo.html`. Catálogo volta ao comportamento original.

---

## 12. Impacto Técnico Consolidado

| Item | Etapa D | Etapa E | Etapa F | Total |
|---|---|---|---|---|
| Arquivos novos | 2 (engine.py, inteligencia.html) | 1 (consumo.html) | 0 | 3 |
| Arquivos alterados | 2 (main.py, base.html) | 1 (main.py) | 1 (catalogo.html) | 3 únicos |
| Novas tabelas | 0 | 0 | 0 | 0 |
| Campos novos em tabelas | 0 | 0 | 0 | 0 |
| Novas rotas | 3 | 3 | 2 | 8 |
| Rotas alteradas | 0 | 0 | 0 | 0 |
| Migrations | 0 | 0 | 0 | 0 |
| Testes de aceite | 12 | 10 | 8 | 30 |
| Dependências externas | 0 | 0 | 0 | 0 |

**Zero migrations, zero novas tabelas, zero dependências externas.**
Toda a inteligência é calculada sobre dados já existentes.

---

## Glossário Técnico

| Termo | Significado no Contexto |
|---|---|
| Dias de Cobertura | `estoque_atual ÷ media_diaria_30d` — quantos dias o estoque aguenta sem produzir |
| Média Móvel | Média de um período deslizante (ex: últimas 4 semanas) para suavizar variações |
| Taxa de Crescimento | `(periodo_atual - periodo_anterior) ÷ periodo_anterior × 100` |
| Confiança ALTA | 5 ou mais pedidos históricos do produto pelo cliente |
| Confiança MEDIA | 2 a 4 pedidos históricos |
| Confiança BAIXA | 1 pedido ou nenhum |
| Status CRÍTICO | Cobertura ≤ 1 dia — produção imediata recomendada |
| Status ALERTA | Cobertura 1–3 dias — produzir esta semana |
| Status PLANEJAR | Cobertura 3–7 dias — incluir no planejamento semanal |
| Status EXCESSO | Cobertura > 21 dias — superprodução detectada |
| Pedido DELIVERED | Único status que conta para cálculos de demanda real |

---

*Fim do documento PRD — SmartFood Ops 360 v4.0 — Módulo de Inteligência Preditiva*  
*Este documento complementa o PRD v3.0 (Usuários, Portal Cliente, QR Code).*
