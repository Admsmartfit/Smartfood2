# PRD — Plano de Melhorias Incrementais
**Sistema:** Academia2 — Agendamento Inteligente + Onboarding  
**Versão:** 1.0  
**Data:** 24/04/2026  
**Princípio:** O sistema está funcional. Cada etapa é autônoma, não quebra o que existe e pode ser revertida isoladamente.

---

## Diagnóstico Rápido do Estado Atual

O sistema já possui uma base sólida:

- ✅ Agendamento avulso e recorrente funcionando
- ✅ Módulo de onboarding (quiz → PAR-Q → demo → conversão)
- ✅ Calendário FullCalendar para o prestador
- ✅ Painel Admin com funil de leads
- ✅ 22 testes críticos passando
- ✅ Modelos preparados para extensão (Notification, AuditLog, ConsentLog vazios)

**O que falta / pode melhorar (sem tocar no que funciona):**

| Gap | Impacto | Complexidade |
|---|---|---|
| `Notification` model vazio — sem notificações reais | Alto | Médio |
| `AuditLog` vazio — sem rastreabilidade | Médio | Baixo |
| `SELECT FOR UPDATE` ausente — race condition em produção | Alto | Baixo |
| Check-in de demo não dispara WhatsApp | Médio | Médio |
| Sem painel financeiro / DRE | Alto | Alto |
| Sem controle de presença/no-show automático | Médio | Baixo |
| Sem NPS pós-aula | Baixo | Baixo |
| Migrations Flask-Migrate não geradas | Médio | Baixo |
| Slug de modalidade no onboarding frágil (ILIKE) | Baixo | Baixo |

---

## Etapa 1 — Correções Críticas de Produção

**Prazo sugerido:** Semana 1  
**Risco de quebra:** Mínimo — são correções pontuais sem alterar APIs existentes.

### 1.1 — Proteção contra Race Condition (SELECT FOR UPDATE)

**Problema:** `validate_booking` em `app/services/scheduling.py` pode aprovar dois clientes para a última vaga antes de qualquer `flush`, conforme demonstrado em `TestConcurrency.test_race_condition_window_both_pass_validation`.

**Solução:** Adicionar bloqueio pessimista na rota `POST /student/book/<slot_id>`.

```python
# Em app/routes/student.py — função book()
# ANTES do validate_booking, adicionar:
slot = (
    ScheduleSlot.query
    .filter_by(id=slot_id)
    .with_for_update()   # ← ÚNICA linha nova
    .first_or_404()
)
```

**Impacto:** Funciona apenas com PostgreSQL. SQLite ignora silenciosamente (sem erro). Antes do deploy em produção com Postgres, trocar a DATABASE_URL e gerar migrations.

**Testes afetados:** Nenhum quebra — `test_race_condition_window_both_pass_validation` continuará passando (documenta a janela de vulnerabilidade com SQLite), mas o comportamento real em produção estará protegido.

---

### 1.2 — Migrations Flask-Migrate

**Problema:** O schema evolui via `db.create_all()` no `run.py`, o que é inseguro em produção.

**O que fazer:**

```bash
# Apenas uma vez, no ambiente de desenvolvimento
flask --app run:app db init
flask --app run:app db migrate -m "initial schema"
flask --app run:app db upgrade
```

Depois, para cada nova coluna/tabela futura:

```bash
flask --app run:app db migrate -m "descricao da mudança"
flask --app run:app db upgrade
```

**Arquivo a alterar:** Nenhum — apenas executar os comandos e commitar a pasta `migrations/`.

---

### 1.3 — Correção do Slug de Modalidade no Onboarding

**Problema:** Em `app/routes/onboarding.py` (função `suggestion`), a busca por modalidade usa `ILIKE` com lógica frágil que pode falhar se o nome da modalidade mudar.

**Solução:** Adicionar um campo `slug` na `Modality` e usá-lo para lookup direto.

**Migration:**

```sql
-- Migration 009
ALTER TABLE modalities ADD COLUMN slug VARCHAR(50);
UPDATE modalities SET slug = LOWER(REPLACE(name, ' ', '_'));
CREATE UNIQUE INDEX idx_modality_slug ON modalities(slug);
```

**Modelo (`app/models/modality.py`):** Adicionar apenas:

```python
slug = db.Column(db.String(50), nullable=True, unique=True)
```

**Onboarding (`app/routes/onboarding.py`):** Substituir o bloco de lookup de modalidade:

```python
# ANTES (frágil):
m = Modality.query.filter(Modality.name.ilike(f"%{slug}%")).first()

# DEPOIS (robusto):
m = Modality.query.filter_by(slug=slug).first()
```

**Seed (`seed.py`):** Adicionar `slug='musculacao'` e `slug='ezbody'` nas modalidades.

---

## Etapa 2 — Sistema de Notificações Interno

**Prazo sugerido:** Semana 2  
**Risco de quebra:** Baixo — implementa o modelo `Notification` que já existe vazio. Nenhuma rota existente muda.

### 2.1 — Implementar o Modelo Notification

Substituir o `pass` em `app/models/notification.py`:

```python
class Notification(db.Model):
    __tablename__ = 'notifications'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type       = db.Column(db.String(50), nullable=False)
    # Valores: 'booking_confirmed' | 'booking_cancelled' | 'demo_completed'
    #          | 'slot_cancelled' | 'no_show' | 'lead_stuck'
    title      = db.Column(db.String(255), nullable=False)
    message    = db.Column(db.Text, nullable=True)
    is_read    = db.Column(db.Boolean, default=False, nullable=False)
    related_id = db.Column(db.Integer, nullable=True)   # booking_id, slot_id etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')
```

**Migration:**

```sql
-- Migration 010
ALTER TABLE notifications ADD COLUMN user_id INTEGER REFERENCES users(id);
ALTER TABLE notifications ADD COLUMN type VARCHAR(50);
ALTER TABLE notifications ADD COLUMN title VARCHAR(255);
ALTER TABLE notifications ADD COLUMN message TEXT;
ALTER TABLE notifications ADD COLUMN is_read BOOLEAN DEFAULT 0;
ALTER TABLE notifications ADD COLUMN related_id INTEGER;
ALTER TABLE notifications ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP;
CREATE INDEX idx_notification_user ON notifications(user_id, is_read);
```

---

### 2.2 — Criar Serviço de Notificações

Novo arquivo `app/services/notifications.py`:

```python
def notify_booking_confirmed(booking):
    """Dispara ao criar um Booking CONFIRMED."""

def notify_booking_cancelled(booking, cancelled_by='client'):
    """Dispara ao cancelar — diferencia cancelamento pelo aluno vs prestador."""

def notify_slot_cancelled(slot, affected_bookings):
    """Dispara quando prestador cancela slot com inscritos."""

def notify_demo_completed(booking):
    """Dispara quando checkin de demo é feito — notifica admin."""

def notify_no_show(booking):
    """Dispara quando status vira NO_SHOW — para followup."""
```

Cada função cria um registro em `Notification`. Não envia WhatsApp ainda (isso é Etapa 4).

---

### 2.3 — Integrar nas Rotas Existentes

**Alterações mínimas — apenas adicionar `notify_*()` após os commits existentes:**

| Arquivo | Função | Ponto de integração |
|---|---|---|
| `app/routes/student.py` | `book()` | Após `db.session.commit()` |
| `app/routes/student.py` | `booking_cancel()` | Após `db.session.commit()` |
| `app/routes/provider.py` | `slot_delete()` | Após `db.session.commit()` |
| `app/routes/provider.py` | `checkin()` | Após `db.session.commit()` |

Exemplo (não altera a lógica existente):

```python
# Em student.py → book() — APENAS ADICIONAR ao final
db.session.commit()
# ↓ nova linha ↓
from app.services.notifications import notify_booking_confirmed
notify_booking_confirmed(booking)
db.session.commit()  # salva a notification
```

---

### 2.4 — Sino de Notificações no Topbar

Adicionar no `base.html` (somente para usuários logados) um ícone com badge de não lidas:

```html
<!-- Em base.html, dentro do <body>, antes do </body> -->
{% if current_user.is_authenticated %}
<div id="notif-bell" style="position:fixed;bottom:70px;right:16px;z-index:500">
  <a href="/notifications" style="
    display:flex;align-items:center;justify-content:center;
    width:44px;height:44px;border-radius:50%;
    background:var(--primary-color);color:#fff;
    box-shadow:0 4px 12px rgba(255,107,53,.4);
    text-decoration:none;font-size:1.1rem;">
    <i class="fas fa-bell"></i>
    {% set unread = current_user.notifications | selectattr('is_read','equalto',false) | list | length %}
    {% if unread > 0 %}
    <span style="position:absolute;top:-4px;right:-4px;
      background:#dc3545;color:#fff;border-radius:50%;
      width:18px;height:18px;font-size:.6rem;font-weight:700;
      display:flex;align-items:center;justify-content:center;">
      {{ unread if unread < 10 else '9+' }}
    </span>
    {% endif %}
  </a>
</div>
{% endif %}
```

**Nova rota** `GET /notifications` — lista simples, marca como lidas ao abrir. Não quebra nada existente.

---

## Etapa 3 — AuditLog e Controle de No-Show

**Prazo sugerido:** Semana 3  
**Risco de quebra:** Zero — são adições puras, sem alterar lógica existente.

### 3.1 — Implementar AuditLog

Substituir o `pass` em `app/models/audit_log.py`:

```python
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action      = db.Column(db.String(100), nullable=False)
    # Valores: 'booking.created' | 'booking.cancelled' | 'slot.cancelled'
    #          | 'lead.converted' | 'checkin' | 'recurring.stopped'
    entity_type = db.Column(db.String(50), nullable=True)   # 'Booking', 'Slot' etc.
    entity_id   = db.Column(db.Integer, nullable=True)
    old_value   = db.Column(db.Text, nullable=True)         # JSON string
    new_value   = db.Column(db.Text, nullable=True)         # JSON string
    ip_address  = db.Column(db.String(45), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
```

**Serviço** `app/services/audit.py` com função única:

```python
def log_action(action, entity_type=None, entity_id=None,
               old_value=None, new_value=None, user_id=None):
    from flask_login import current_user
    from flask import request
    entry = AuditLog(
        user_id=user_id or (current_user.id if current_user.is_authenticated else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=json.dumps(old_value) if old_value else None,
        new_value=json.dumps(new_value) if new_value else None,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)
    # Não faz commit — o caller decide
```

---

### 3.2 — No-Show Automático

**Problema atual:** Bookings nunca viram `NO_SHOW` automaticamente.

**Solução:** Tarefa agendada simples. Criar `app/tasks.py`:

```python
def mark_no_shows():
    """
    Marcar como NO_SHOW bookings CONFIRMED cujo slot terminou há mais de 15 min
    e o aluno não fez check-in (checked_in_at is None).
    Rodar via cron ou APScheduler a cada 30 minutos.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=15)

    stale = (
        Booking.query
        .join(ScheduleSlot)
        .filter(
            Booking.status == BookingStatus.CONFIRMED,
            Booking.checked_in_at == None,
            ScheduleSlot.status != 'cancelled',
            db.func.datetime(
                ScheduleSlot.date, ' ', ScheduleSlot.end_time
            ) < cutoff.isoformat(),
        )
        .all()
    )
    for b in stale:
        b.status = BookingStatus.NO_SHOW
        notify_no_show(b)

    db.session.commit()
    return len(stale)
```

**Para rodar em desenvolvimento** (sem cron), adicionar em `run.py` usando APScheduler:

```python
# pip install apscheduler
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(mark_no_shows_with_context, 'interval', minutes=30)
scheduler.start()
```

**Nenhuma rota existente é alterada.**

---

### 3.3 — Página de Audit Trail no Admin

Nova rota `GET /admin/audit` — tabela simples com filtros por usuário, ação e data.  
Reutiliza os mesmos componentes visuais de `admin/leads/index.html`.  
**Não altera nenhuma rota existente.**

---

## Etapa 4 — Integração WhatsApp (Notificações Externas)

**Prazo sugerido:** Semana 4–5  
**Risco de quebra:** Zero — é uma camada adicional por cima das notificações internas da Etapa 2.  
**Pré-requisito:** Etapa 2 concluída.

### 4.1 — Estrutura

Criar `app/services/whatsapp.py` com uma função de despacho única:

```python
WHATSAPP_API_URL = os.environ.get('WHATSAPP_API_URL')   # ex: Evolution API, Z-API
WHATSAPP_TOKEN   = os.environ.get('WHATSAPP_TOKEN')

def send_whatsapp(phone: str, message: str) -> bool:
    """
    Envia mensagem via HTTP POST para a API configurada.
    Retorna True em sucesso, False em falha (não lança exceção — nunca
    quebra o fluxo principal da aplicação).
    """
    if not WHATSAPP_API_URL or not WHATSAPP_TOKEN:
        return False   # Silencioso quando não configurado
    try:
        res = requests.post(...)
        return res.status_code == 200
    except Exception:
        return False
```

---

### 4.2 — Templates de Mensagem

```python
# app/services/whatsapp_templates.py

def msg_booking_confirmed(booking):
    slot = booking.slot
    return (
        f"✅ *Aula confirmada!*\n"
        f"📅 {slot.date.strftime('%d/%m/%Y')} às {slot.start_time.strftime('%H:%M')}\n"
        f"🏋️ {slot.modality.name if slot.modality else 'Aula'}\n"
        f"👤 {slot.provider.name if slot.provider else ''}\n\n"
        f"Para cancelar acesse o app com até {deadline}h de antecedência."
    )

def msg_booking_cancelled_by_provider(booking):
    ...

def msg_demo_completed(booking):
    ...

def msg_no_show_followup(booking):
    ...
```

---

### 4.3 — Integração com Serviço de Notificações

Em `app/services/notifications.py`, adicionar chamada ao final de cada `notify_*`:

```python
def notify_booking_confirmed(booking):
    # ... cria Notification interna (já existia) ...

    # ↓ NOVO — adicionar ao final ↓
    from app.services.whatsapp import send_whatsapp
    from app.services.whatsapp_templates import msg_booking_confirmed
    if booking.client and booking.client.phone:
        send_whatsapp(booking.client.phone, msg_booking_confirmed(booking))
```

Se `WHATSAPP_API_URL` não estiver configurada, `send_whatsapp` retorna `False` silenciosamente. **Nenhuma funcionalidade existente é afetada.**

---

### 4.4 — Painel de Status WhatsApp no Admin

Adicionar ao `admin/leads/funnel.html` um card simples:

- Total de mensagens enviadas (hoje / semana)
- Total de falhas
- Botão "Testar conexão"

Dados vindos de uma nova tabela `WhatsappLog` (id, phone, message_type, status, created_at) — pequena e independente.

---

## Etapa 5 — Módulo Financeiro Básico (DRE Simplificado)

**Prazo sugerido:** Semana 6–7  
**Risco de quebra:** Zero — implementa o modelo `Expense` que já existe vazio, e lê dados de modelos existentes.

### 5.1 — Implementar Expense

```python
class Expense(db.Model):
    __tablename__ = 'expenses'

    id           = db.Column(db.Integer, primary_key=True)
    description  = db.Column(db.String(255), nullable=False)
    category     = db.Column(db.String(50), nullable=False)
    # Categorias: 'aluguel' | 'folha' | 'equipamento' | 'marketing' | 'outros'
    amount       = db.Column(db.Numeric(10, 2), nullable=False)
    date         = db.Column(db.Date, nullable=False)
    is_recurring = db.Column(db.Boolean, default=False)
    created_by_id= db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
```

---

### 5.2 — Receita (leitura dos dados existentes)

A receita já está implícita nos `Booking.cost_at_booking` e no preço dos pacotes de crédito. Criar uma view de leitura que agrega:

```python
def get_revenue_summary(start_date, end_date):
    """
    Agrega bookings confirmados/completados no período.
    Retorna: { 'total_bookings': X, 'total_credits': Y }
    Sem tocar no schema — apenas SELECT.
    """
```

---

### 5.3 — Dashboard Financeiro

Nova rota `GET /admin/finance` com três cards:

- **Receita estimada** (créditos × preço médio por crédito configurável)
- **Despesas** (soma das `Expense` do mês)
- **Margem bruta estimada**

Gráfico de linha simples (Chart.js — já disponível via CDN) mostrando os últimos 6 meses.

**Rotas novas:**

```
GET  /admin/finance                 → Dashboard financeiro
GET  /admin/finance/expenses        → Lista de despesas
POST /admin/finance/expenses/create → Criar despesa
POST /admin/finance/expenses/<id>/delete → Remover despesa
```

---

## Etapa 6 — Melhorias de UX no Agendamento

**Prazo sugerido:** Semana 8  
**Risco de quebra:** Baixo — são melhorias visuais e de UX na `student/schedule.html` sem alterar as APIs existentes.

### 6.1 — Filtro por Turno no Calendário Principal

O filtro de turno já existe no onboarding (`filter_slots_by_turno`). Está parcialmente integrado em `student/schedule.html` mas não aparece no calendário da esquerda.

**Ajuste:** O select `#sel-turno` já existe em `filter-bar`. Garantir que `onFilterChange()` invalide `summaryCache` e recarregue os dots do calendário com o filtro aplicado. **Zero linha nova no backend** — a rota `/student/api/availability/summary` já aceita `turno` como parâmetro.

---

### 6.2 — Indicador de Créditos no Topbar do Aluno

Adicionar ao topbar de `student/schedule.html` o saldo de créditos de forma visível:

```html
<!-- Em .sch-topbar, ao lado do link "Reservas" -->
{% if active_subs %}
{% set total_credits = active_subs | map(attribute='credits_remaining') | sum %}
<span style="font-size:.75rem;background:rgba(255,255,255,.2);
  padding:3px 10px;border-radius:20px;color:#fff">
  <i class="fas fa-star me-1"></i>{{ total_credits }} crédito{{ 's' if total_credits != 1 }}
</span>
{% endif %}
```

**Uma linha no template. Nenhum backend alterado.**

---

### 6.3 — Confirmação Visual Pós-Agendamento

Atualmente, após agendar, o card muda de estado via JS, mas não há feedback sonoro/visual marcante. Adicionar uma animação de confetti leve (CSS puro, sem biblioteca) e um som opcional.

**Implementação:** Apenas JS/CSS no arquivo `schedule.html`. Nenhum backend envolvido.

---

### 6.4 — Página de Perfil do Aluno

Nova rota `GET /student/profile` e `POST /student/profile/update` para o aluno editar nome, telefone e senha. Usa apenas o modelo `User` existente.

```
GET  /student/profile           → Formulário de perfil
POST /student/profile/update    → Atualiza name, phone, password
```

Template reutiliza os componentes visuais do `onboarding/set_password.html`.

---

## Etapa 7 — ConsentLog (LGPD) e Exportação de Dados

**Prazo sugerido:** Semana 9  
**Risco de quebra:** Zero — adição pura.

### 7.1 — Implementar ConsentLog

```python
class ConsentLog(db.Model):
    __tablename__ = 'consent_logs'

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    consent_type = db.Column(db.String(50), nullable=False)
    # Valores: 'terms_of_service' | 'privacy_policy' | 'marketing_whatsapp' | 'parq'
    accepted     = db.Column(db.Boolean, nullable=False)
    version      = db.Column(db.String(20), nullable=True)   # ex: 'v1.0'
    ip_address   = db.Column(db.String(45), nullable=True)
    user_agent   = db.Column(db.String(255), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
```

---

### 7.2 — Coleta de Consentimento no Quiz

No primeiro passo do quiz (`onboarding/quiz.html`), antes do botão "Próximo" da pergunta 1, adicionar:

```html
<label style="font-size:.73rem;color:#6c757d;display:flex;gap:8px;margin-top:12px">
  <input type="checkbox" id="consent-check" required>
  Concordo com os <a href="/terms" target="_blank">Termos de Uso</a> e
  <a href="/privacy" target="_blank">Política de Privacidade</a>
</label>
```

Ao submeter o quiz, registrar em `ConsentLog`. **Nenhuma lógica existente muda** — apenas adicionar `log_consent('terms_of_service', accepted=True)` em `quiz_submit()`.

---

### 7.3 — Exportação de Dados (Direito de Portabilidade)

Nova rota `GET /student/export-data` que gera um JSON com todos os dados do usuário:

```json
{
  "user": { "name": "...", "email": "...", "phone": "..." },
  "bookings": [ { "date": "...", "modality": "...", "status": "..." } ],
  "lead_profile": { "objetivo": "...", "quiz_completed_at": "..." },
  "consents": [ { "type": "...", "accepted": true, "date": "..." } ]
}
```

Retorna como download de arquivo. **Leitura pura, sem alterar nenhum dado.**

---

## Resumo de Impacto por Etapa

| Etapa | Arquivos novos | Arquivos alterados | Migrations novas | Testes novos |
|---|---|---|---|---|
| 1 — Correções críticas | 0 | 3 | 1 | 0 (existentes cobrem) |
| 2 — Notificações internas | 2 | 5 | 1 | 3 |
| 3 — AuditLog + No-Show | 2 | 2 | 1 | 2 |
| 4 — WhatsApp | 2 | 1 | 1 | 2 |
| 5 — Financeiro | 1 | 1 | 1 | 2 |
| 6 — UX Agendamento | 0 | 2 templates | 0 | 0 |
| 7 — LGPD + Exportação | 1 | 2 | 1 | 1 |

**Total:** 8 arquivos novos, 16 alterados, 6 migrations, 10 testes novos — distribuídos em 9 semanas.

---

## Regras de Ouro para Implementação

1. **Nunca alterar uma rota que funciona.** Adicionar novas rotas ao lado, nunca refatorar as existentes sem cobertura de teste.

2. **Cada etapa começa com migration versionada.** Nunca usar `db.create_all()` após a Etapa 1.

3. **Serviços externos (WhatsApp) são sempre opcionais.** Se `WHATSAPP_API_URL` não estiver no `.env`, tudo funciona normalmente.

4. **Testes antes do deploy.** Rodar `pytest tests/test_critical.py -v` após cada etapa — 22 testes devem continuar passando.

5. **Feature flags por variável de ambiente.** Para funcionalidades experimentais, usar `os.environ.get('FEATURE_X', False)` para ativar/desativar sem deploy.
