"""
intelligence_engine.py — Motor de Inteligência Preditiva SmartFood v4.0

Estatística descritiva simples, zero dependências externas além de
datetime, collections e SQLAlchemy (já presente no projeto).

Princípio: apenas pedidos com status='DELIVERED' contam como consumo real.
"""

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import Recipe, SalesOrder, SalesOrderItem


# ── 1. Demanda por Produto ────────────────────────────────────────────────────

def calcular_demanda_produto(recipe_id: int, db: Session, janela_dias: int = 30) -> dict:
    """Calcula métricas de demanda para um produto no período informado."""
    desde = datetime.utcnow() - timedelta(days=janela_dias)

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

    semanas: dict[str, float] = {}
    total = 0.0
    for item in itens:
        semana_key = item.order.order_date.strftime("%Y-W%W")
        semanas[semana_key] = semanas.get(semana_key, 0) + item.quantity
        total += item.quantity

    valores_semanais = list(semanas.values()) if semanas else [0.0]
    media_diaria = total / janela_dias if janela_dias > 0 else 0

    return {
        "recipe_id": recipe_id,
        "total_unidades_vendidas": total,
        "media_diaria": round(media_diaria, 2),
        "media_semanal": round(media_diaria * 7, 2),
        "dias_com_pedido": len({item.order.order_date.date() for item in itens}),
        "pico_semanal": max(valores_semanais),
        "minimo_semanal": min(valores_semanais),
        "semanas_com_dados": len(semanas),
    }


# ── 2. Taxa de Crescimento ────────────────────────────────────────────────────

def calcular_taxa_crescimento(
    recipe_id: int,
    db: Session,
    customer_id: int | None = None,
) -> dict:
    """Compara consumo do período atual com o anterior (semana vs. semana, mês vs. mês)."""
    agora = datetime.utcnow()

    def soma_periodo(inicio, fim):
        q = (
            db.query(func.sum(SalesOrderItem.quantity))
            .join(SalesOrder)
            .filter(
                SalesOrderItem.recipe_id == recipe_id,
                SalesOrder.status == "DELIVERED",
                SalesOrder.order_date >= inicio,
                SalesOrder.order_date < fim,
            )
        )
        if customer_id is not None:
            q = q.filter(SalesOrder.customer_id == customer_id)
        return float(q.scalar() or 0)

    sem_atual_ini   = agora - timedelta(days=7)
    sem_ant_ini     = agora - timedelta(days=14)
    sem_atual       = soma_periodo(sem_atual_ini, agora)
    sem_anterior    = soma_periodo(sem_ant_ini, sem_atual_ini)

    mes_atual_ini   = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    mes_ant_ini     = (mes_atual_ini - timedelta(days=1)).replace(day=1)
    mes_atual       = soma_periodo(mes_atual_ini, agora)
    mes_anterior    = soma_periodo(mes_ant_ini, mes_atual_ini)

    def variacao(atual, anterior):
        if anterior == 0:
            return 100.0 if atual > 0 else 0.0
        return round(((atual - anterior) / anterior) * 100, 1)

    def tendencia(v):
        if v > 10:  return "CRESCENDO"
        if v < -10: return "CAINDO"
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


# ── 3. Urgência de Produção ───────────────────────────────────────────────────

def calcular_urgencia_producao(recipe_id: int, db: Session) -> dict:
    """Combina estoque atual com demanda média para calcular urgência de produção."""
    recipe = db.query(Recipe).filter_by(id=recipe_id).first()
    if not recipe:
        return {}

    demanda     = calcular_demanda_produto(recipe_id, db, janela_dias=30)
    media_diaria = demanda["media_diaria"]
    estoque     = recipe.current_stock_units or 0
    rendimento  = max(1, recipe.rendimento_unidades or 1)

    dias_cobertura = (estoque / media_diaria) if media_diaria > 0 else 999.0

    if media_diaria == 0:
        urgencia = "SEM_DEMANDA"
        sugestao = 0
        producao_para_dias = 0
        justificativa = "Sem histórico de vendas nos últimos 30 dias."
    elif dias_cobertura <= 1:
        urgencia = "CRITICO"
        producao_para_dias = 14
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
        sugestao = max(0, int(media_diaria * producao_para_dias - estoque))
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
        "recipe_name": recipe.nome_comercial or recipe.name,
        "recipe_name_raw": recipe.name,
        "estoque_atual": estoque,
        "media_diaria_30d": media_diaria,
        "dias_cobertura": round(dias_cobertura if dias_cobertura != 999.0 else 0, 1),
        "dias_cobertura_real": dias_cobertura,
        "urgencia": urgencia,
        "sugestao_producao": sugestao,
        "sugestao_lotes": sugestao_lotes,
        "producao_para_dias": producao_para_dias,
        "justificativa": justificativa,
    }


# ── 4. Sugestão de Pedido para Cliente ───────────────────────────────────────

def calcular_sugestao_pedido_cliente(
    recipe_id: int,
    customer_id: int,
    db: Session,
) -> dict:
    """Calcula sugestão de quantidade para um cliente específico."""
    desde_90d = datetime.utcnow() - timedelta(days=90)

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
            "media_semanal_pacotes": 0.0,
            "confianca": "BAIXA",
            "historico_pedidos": 0,
            "mensagem": "Sem histórico de compra deste produto.",
            "ultimo_pedido_qtd": 0,
            "dias_desde_ultimo_pedido": 999,
        }

    total_qtd   = sum(i.quantity for i in itens)
    media_semanal = total_qtd / 13  # 90 dias ≈ 13 semanas

    ultimo_item  = itens[0]
    ultimo_data  = ultimo_item.order.order_date.date()
    dias_desde   = (datetime.utcnow().date() - ultimo_data).days

    sugestao = max(1, round(media_semanal))
    if dias_desde > 14:
        sugestao = max(sugestao, round(media_semanal * 1.2))

    confianca = (
        "ALTA"  if len(itens) >= 5 else
        "MEDIA" if len(itens) >= 2 else
        "BAIXA"
    )

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
        "ultimo_pedido_data": str(ultimo_data),
        "dias_desde_ultimo_pedido": dias_desde,
        "sugestao_pacotes": sugestao,
        "confianca": confianca,
        "historico_pedidos": len(itens),
        "mensagem": mensagem,
    }


# ── 5. Série Histórica ────────────────────────────────────────────────────────

def serie_historica_cliente(
    customer_id: int | None,
    db: Session,
    recipe_id: int | None = None,
    granularidade: str = "semana",
    janela_semanas: int = 12,
) -> list[dict]:
    """Retorna série temporal de consumo. customer_id=None agrega todos os clientes."""
    desde = datetime.utcnow() - timedelta(weeks=janela_semanas)

    q = (
        db.query(SalesOrderItem, SalesOrder)
        .join(SalesOrder)
        .filter(
            SalesOrder.status == "DELIVERED",
            SalesOrder.order_date >= desde,
        )
    )
    if customer_id is not None:
        q = q.filter(SalesOrder.customer_id == customer_id)
    if recipe_id is not None:
        q = q.filter(SalesOrderItem.recipe_id == recipe_id)

    resultados = q.all()

    agregado: dict[str, dict] = {}
    pedidos_por_periodo: dict[str, set] = {}

    for item, order in resultados:
        if granularidade == "mes":
            chave = order.order_date.strftime("%Y-%m")
            label = order.order_date.strftime("%b/%Y").capitalize()
        else:
            chave = order.order_date.strftime("%Y-W%W")
            semana_num = order.order_date.isocalendar()[1]
            label = f"S{semana_num}/{order.order_date.year}"

        if chave not in agregado:
            agregado[chave] = {
                "periodo": chave,
                "periodo_label": label,
                "quantidade": 0.0,
                "valor_total": 0.0,
                "num_pedidos": 0,
            }
            pedidos_por_periodo[chave] = set()

        agregado[chave]["quantidade"]  += item.quantity
        agregado[chave]["valor_total"] += item.quantity * item.unit_price
        pedidos_por_periodo[chave].add(order.id)

    for chave in agregado:
        agregado[chave]["num_pedidos"] = len(pedidos_por_periodo[chave])
        agregado[chave]["valor_total"] = round(agregado[chave]["valor_total"], 2)

    return sorted(agregado.values(), key=lambda x: x["periodo"])


# ── 6. Plano de Produção Semanal ─────────────────────────────────────────────

_ORDEM_URGENCIA = {
    "CRITICO": 1, "ALERTA": 2, "PLANEJAR": 3,
    "OK": 4, "EXCESSO": 5, "SEM_DEMANDA": 6,
}

def gerar_plano_producao_semanal(db: Session) -> list[dict]:
    """Itera todos os produtos e gera lista priorizada de produção."""
    recipes = db.query(Recipe).order_by(Recipe.name).all()
    plano = []

    for recipe in recipes:
        urgencia = calcular_urgencia_producao(recipe.id, db)
        if not urgencia:
            continue
        crescimento = calcular_taxa_crescimento(recipe.id, db)
        plano.append({
            **urgencia,
            "urgencia_ordem": _ORDEM_URGENCIA.get(urgencia.get("urgencia", "OK"), 4),
            "media_semanal": urgencia.get("media_diaria_30d", 0) * 7,
            "crescimento_pct": crescimento.get("variacao_semanal_pct", 0),
            "tendencia": crescimento.get("tendencia_semanal", "ESTAVEL"),
        })

    return sorted(plano, key=lambda x: (x["urgencia_ordem"], -x.get("media_semanal", 0)))


# ── 7. Produtos do Cliente (aux) ─────────────────────────────────────────────

def produtos_do_cliente(customer_id: int, db: Session) -> list[dict]:
    """Lista produtos comprados pelo cliente nos últimos 90 dias."""
    desde = datetime.utcnow() - timedelta(days=90)

    rows = (
        db.query(
            SalesOrderItem.recipe_id,
            Recipe.name.label("recipe_name"),
            (Recipe.nome_comercial).label("recipe_nome_comercial"),
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

    agora = datetime.utcnow()
    return [
        {
            "recipe_id": r.recipe_id,
            "recipe_name": r.recipe_nome_comercial or r.recipe_name,
            "quantidade_total": float(r.quantidade_total or 0),
            "ultimo_pedido": r.ultimo_pedido,
            "dias_desde_ultimo": (agora - r.ultimo_pedido).days if r.ultimo_pedido else 999,
            "num_pedidos": r.num_pedidos,
        }
        for r in rows
    ]


# ── 8. Gráfico SVG ───────────────────────────────────────────────────────────

def gerar_grafico_svg(
    serie: list[dict],
    largura: int = 500,
    altura: int = 160,
    cor: str = "#2563eb",
) -> str:
    """Gera SVG de linha para a série histórica. Retorna string segura para | safe."""
    if not serie:
        return '<p style="color:#94a3b8;font-size:.8rem;padding:1rem">Sem dados suficientes.</p>'

    valores = [s["quantidade"] for s in serie]
    labels  = [s["periodo_label"] for s in serie]
    n = len(valores)

    max_val = max(valores) if any(v > 0 for v in valores) else 1.0
    min_val = min(valores)

    pad_x, pad_y = 44, 16
    w = largura - pad_x * 2
    h = altura  - pad_y * 2 - 16   # 16px para labels do eixo X

    def cx(i):
        return pad_x + (i / max(n - 1, 1)) * w

    def cy(v):
        span = max_val - min_val
        if span == 0:
            return pad_y + h / 2
        return pad_y + h - ((v - min_val) / span) * h

    pontos_poly = " ".join(f"{cx(i):.1f},{cy(v):.1f}" for i, v in enumerate(valores))
    pontos_area = (
        f"{cx(0):.1f},{pad_y + h} "
        f"{pontos_poly} "
        f"{cx(n-1):.1f},{pad_y + h}"
    )

    circles = "".join(
        f'<circle cx="{cx(i):.1f}" cy="{cy(v):.1f}" r="3.5" fill="{cor}"/>'
        for i, v in enumerate(valores)
    )

    # Tooltip invisível (title tag)
    tooltips = "".join(
        f'<circle cx="{cx(i):.1f}" cy="{cy(v):.1f}" r="8" fill="transparent">'
        f'<title>{labels[i]}: {v:.0f}</title></circle>'
        for i, v in enumerate(valores)
    )

    # Eixo X: primeiro, meio e último
    idx_labels = sorted({0, n // 2, n - 1}) if n > 1 else [0]
    eixo_x = "".join(
        f'<text x="{cx(i):.1f}" y="{altura - 3}" text-anchor="middle" '
        f'font-size="9" fill="#94a3b8" font-family="Inter,sans-serif">{labels[i]}</text>'
        for i in idx_labels if i < n
    )

    # Linhas de grade horizontais (3 linhas)
    grid = ""
    for frac in (0.25, 0.5, 0.75):
        yg = pad_y + h * (1 - frac)
        val = min_val + (max_val - min_val) * frac
        grid += (
            f'<line x1="{pad_x}" y1="{yg:.1f}" x2="{pad_x + w}" y2="{yg:.1f}" '
            f'stroke="#334155" stroke-width="0.5" stroke-dasharray="3,3"/>'
            f'<text x="{pad_x - 4}" y="{yg + 3:.1f}" text-anchor="end" '
            f'font-size="8" fill="#64748b" font-family="Inter,sans-serif">{val:.0f}</text>'
        )

    grad_id = f"g{abs(hash(str(serie[:2]))) % 9999}"
    return f"""<svg width="100%" viewBox="0 0 {largura} {altura}"
     xmlns="http://www.w3.org/2000/svg" style="overflow:visible;display:block">
  <defs>
    <linearGradient id="{grad_id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{cor}" stop-opacity="0.18"/>
      <stop offset="100%" stop-color="{cor}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  {grid}
  <polygon points="{pontos_area}" fill="url(#{grad_id})"/>
  <polyline points="{pontos_poly}" fill="none" stroke="{cor}"
            stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  {circles}
  {tooltips}
  {eixo_x}
</svg>"""
