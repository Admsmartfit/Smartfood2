# PRD — SmartFood Ops 360 v3.0
## Gestão de Usuários · Portal do Cliente B2B · Experiência QR Code

**Sistema:** SmartFood Ops 360  
**Versão:** 3.0  
**Data:** Maio 2026  
**Autor:** Produto  
**Status:** Aprovado para Desenvolvimento  
**Princípio-guia:** Cada etapa é autônoma, não quebra o que existe e pode ser revertida isoladamente.

---

## Índice

1. [Diagnóstico e Contexto](#1-diagnóstico-e-contexto)
2. [Personas e Níveis de Acesso](#2-personas-e-níveis-de-acesso)
3. [Escopo da Versão 3.0](#3-escopo-da-versão-30)
4. [Etapa A — Gestão de Usuários](#4-etapa-a--gestão-de-usuários)
5. [Etapa B — Portal do Cliente B2B](#5-etapa-b--portal-do-cliente-b2b)
6. [Etapa C — Guia do Produto via QR Code](#6-etapa-c--guia-do-produto-via-qr-code)
7. [Requisitos de Design](#7-requisitos-de-design)
8. [Especificação Técnica](#8-especificação-técnica)
9. [Critérios de Aceite](#9-critérios-de-aceite)
10. [Plano de Implementação](#10-plano-de-implementação)
11. [Impacto Técnico Consolidado](#11-impacto-técnico-consolidado)
12. [Dependências e Pré-condições](#12-dependências-e-pré-condições)

---

## 1. Diagnóstico e Contexto

### 1.1 Estado Atual da Plataforma

O SmartFood Ops 360 já possui uma base sólida e funcional:

| Módulo | Status |
|---|---|
| Cadastro de Insumos, Marcas e Fornecedores | ✅ Funcionando |
| Ficha Técnica com BOM, FC, FCoc e Margem | ✅ Funcionando |
| Dashboard de Margens com Alertas | ✅ Funcionando |
| Lista de Compras por Fornecedor + WhatsApp | ✅ Funcionando |
| Módulo de Etiquetas e QR Code Dinâmico | ✅ Funcionando |
| Controle de Estoque (Insumos e Produtos) | ✅ Funcionando |
| Clientes e Pedidos de Venda | ✅ Funcionando |
| Módulo de Produção / Cozinha (KDS) | ✅ Funcionando |

### 1.2 Gaps Identificados — Versão 3.0

| Gap | Módulo | Impacto | Complexidade |
|---|---|---|---|
| Sistema sem autenticação — qualquer pessoa acessa tudo | Segurança | Crítico | Médio |
| Clientes pedem reposição por WhatsApp/telefone (ineficiente) | Vendas | Alto | Alto |
| QR Code redireciona para URL genérica; não há Guia do Produto | Produto | Alto | Médio |
| Sem identidade visual separada para o cliente externo | UX | Alto | Médio |
| Sem onboarding para cliente criar conta própria | Vendas | Médio | Baixo |

---

## 2. Personas e Níveis de Acesso

O sistema v3.0 terá **três níveis de acesso distintos**, com rotas, layouts e permissões diferentes:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SmartFood Ops 360                            │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │  PRODUÇÃO /     │  │  CLIENTE        │  │  PÚBLICO            │ │
│  │  ADMIN          │  │  (Logado)       │  │  (QR Code)          │ │
│  │                 │  │                 │  │                     │ │
│  │  Acesso total   │  │  Apenas Portal  │  │  Sem senha          │ │
│  │  ao ERP interno │  │  de Compras B2B │  │  Guia do Produto    │ │
│  │                 │  │                 │  │  via embalagem      │ │
│  │  /dashboard     │  │  /loja          │  │  /produto/{id}      │ │
│  │  /fichas        │  │  /loja/carrinho │  │                     │ │
│  │  /estoque       │  │  /loja/pedidos  │  │  Modo Preparo       │ │
│  │  /producao      │  │                 │  │  Apresentação       │ │
│  │  /admin/users   │  │  Sem acesso a   │  │  Nomes p/ Cardápio  │ │
│  │                 │  │  custos, fichas │  │  Rastreabilidade    │ │
│  │  Login:         │  │  ou estoque     │  │                     │ │
│  │  email + senha  │  │                 │  │  ❌ Sem login       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Persona: Administrador / Produção

**Quem é:** Dono da fábrica, gerente de produção, cozinheira sênior.  
**Necessidade:** Acesso completo ao sistema ERP existente.  
**Diferença do atual:** Agora faz login antes de acessar qualquer módulo.  
**Não muda:** Nenhuma tela do ERP é alterada.

### 2.2 Persona: Cliente B2B (Bar / Restaurante)

**Quem é:** Dono de bar, restaurante ou lanchonete que compra regularmente.  
**Necessidade:** Ver o catálogo de produtos, preços do seu contrato, adicionar ao carrinho e fechar pedido.  
**Restrição:** Vê apenas o Portal de Compras — **nunca** vê custos de produção, fichas técnicas, margens ou estoque interno.  
**Identidade:** Acessa com e-mail e senha criados pelo Administrador (ou via link de convite).

### 2.3 Persona: Público / QR Code (Consumidor do Bar)

**Quem é:** Garçom, cozinheiro do bar ou dono que escaneia o QR da embalagem no momento do recebimento.  
**Necessidade:** Saber como preparar, como apresentar e como nomear o produto no cardápio.  
**Restrição total:** Sem login. Sem dados sensíveis de custo. URL pública.

---

## 3. Escopo da Versão 3.0

Esta versão entrega **três etapas independentes** que podem ser implantadas em qualquer ordem:

```
Etapa A — Gestão de Usuários    →  models.py + main.py + templates/login.html
Etapa B — Portal do Cliente B2B →  templates/loja/*.html + main.py (novas rotas /loja)
Etapa C — Guia do Produto QR    →  templates/public/produto.html + main.py (rota /produto/{id})
```

**Sem migrations destrutivas.** Todas as etapas adicionam tabelas novas ou campos novos (idempotentes via ALTER TABLE).

---

## 4. Etapa A — Gestão de Usuários

### 4.1 Modelo de Dados

**Nova tabela: `users`**

```sql
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nome            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    senha_hash      TEXT    NOT NULL,
    tipo_usuario    TEXT    NOT NULL DEFAULT 'CLIENTE',  -- 'ADMIN' | 'PRODUCAO' | 'CLIENTE'
    cliente_id      INTEGER REFERENCES customers(id),    -- apenas para tipo CLIENTE
    ativo           INTEGER NOT NULL DEFAULT 1,
    criado_em       DATETIME DEFAULT CURRENT_TIMESTAMP,
    ultimo_acesso   DATETIME
);
```

**Vinculação com tabela existente `customers`:**

O campo `cliente_id` faz o link entre o usuário de login e o cadastro de cliente já existente. Isso significa que o histórico de pedidos, tabela de preços e limite de crédito ficam no `Customer`, enquanto as credenciais ficam em `User`.

**Tipos de Usuário:**

| tipo_usuario | Acesso |
|---|---|
| ADMIN | Tudo — incluindo gerenciamento de usuários |
| PRODUCAO | Todo ERP interno — sem gestão de usuários |
| CLIENTE | Apenas /loja/* |

### 4.2 Autenticação — SessionMiddleware

**Biblioteca:** `itsdangerous` para assinar tokens de sessão (já compatível com FastAPI via `starlette.middleware.sessions.SessionMiddleware`).

**Dependência adicional no `requirements.txt`:**
```
starlette[full]
passlib[bcrypt]
```

**Fluxo de Login:**

```
1. GET  /login          → Exibe formulário de login
2. POST /login          → Valida email + senha_hash
                          → Se ADMIN ou PRODUCAO: redirect /dashboard
                          → Se CLIENTE: redirect /loja
                          → Se inválido: erro inline (sem reload)
3. GET  /logout         → Limpa sessão → redirect /login
4. GET  /               → Middleware verifica sessão → redirect /login se não autenticado
```

**Proteção de Rotas:**

```python
# Dependency a ser aplicada em todas as rotas protegidas
async def require_auth(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user_id

async def require_admin(request: Request):
    tipo = request.session.get("tipo_usuario")
    if tipo not in ("ADMIN", "PRODUCAO"):
        raise HTTPException(status_code=403)

async def require_cliente(request: Request):
    tipo = request.session.get("tipo_usuario")
    if tipo != "CLIENTE":
        raise HTTPException(status_code=403)
```

### 4.3 Interface — Tela de Login

**URL:** `/login`  
**Acesso:** Público (sem sessão)

**Campos:**
- E-mail (input type="email", required)
- Senha (input type="password", required)
- Botão "Entrar"
- Link "Esqueci minha senha" (futuro — fase 2)

**Comportamento de erro:** Mensagem inline `"E-mail ou senha incorretos."` — sem revelar qual campo está errado (segurança).

**Design:**
- Página full-screen, sem sidebar
- Logo SmartFood centralizado
- Card central com sombra
- Fundo com textura sutil (gradiente radial)
- Botão de 48px de altura mínima

### 4.4 Interface — Gestão de Usuários (Admin)

**URL:** `/admin/usuarios`  
**Acesso:** Apenas ADMIN

**Funcionalidades:**

| Ação | Detalhe |
|---|---|
| Listar usuários | Tabela com: nome, e-mail, tipo, cliente vinculado, ativo/inativo, último acesso |
| Criar usuário | Modal com: nome, e-mail, senha temporária, tipo, cliente vinculado (se CLIENTE) |
| Editar usuário | Inline: nome, e-mail, tipo, cliente vinculado, ativo/inativo |
| Resetar senha | Gera senha temporária e exibe para o admin copiar/enviar |
| Desativar | Toggle ativo/inativo (não exclui dados) |

**Regras de negócio:**

- Não é possível ter dois usuários com o mesmo e-mail.
- Um usuário tipo CLIENTE **deve** ter um `cliente_id` vinculado.
- Um usuário tipo ADMIN ou PRODUCAO **não deve** ter `cliente_id`.
- O admin não pode desativar a si mesmo.
- Senha mínima: 8 caracteres (validação no frontend e backend).

### 4.5 Rotas Backend — Etapa A

| Método | URL | Função |
|---|---|---|
| GET | `/login` | Página de login |
| POST | `/login` | Processar autenticação |
| GET | `/logout` | Encerrar sessão |
| GET | `/admin/usuarios` | Listar usuários |
| POST | `/admin/usuarios` | Criar usuário |
| PUT | `/admin/usuarios/{id}` | Editar usuário |
| POST | `/admin/usuarios/{id}/reset-senha` | Resetar senha |
| DELETE | `/admin/usuarios/{id}` | Desativar usuário |

### 4.6 Arquivos Alterados/Criados — Etapa A

| Arquivo | Natureza |
|---|---|
| `models.py` | Nova classe `User` |
| `main.py` | SessionMiddleware, rotas /login, /logout, /admin/usuarios, dependencies |
| `requirements.txt` | Adicionar `passlib[bcrypt]` |
| `templates/login.html` | Página nova — sem extends base.html (layout full-screen) |
| `templates/admin/usuarios.html` | Página nova — extends base.html |
| `templates/base.html` | Adicionar link "Usuários" na sidebar (seção Administração) + exibir nome do usuário logado no header |

---

## 5. Etapa B — Portal do Cliente B2B

### 5.1 Problema Detalhado

Hoje o processo de reposição de estoque do cliente (bar/restaurante) é assim:

1. Cliente liga ou manda WhatsApp descrevendo o que quer.
2. Operador anota, consulta estoque, verifica preço do contrato do cliente.
3. Digitam o pedido no sistema.
4. Confirmam por WhatsApp.

Este fluxo tem 4 pontos de falha humana, demora em média 20-40 minutos e não escala.

### 5.2 Solução

Criar um portal de compras self-service dentro do SmartFood, acessível por login do tipo CLIENTE, com:

- Catálogo visual de produtos (fotos de alta qualidade, nome comercial, preço do contrato do cliente)
- Seleção de quantidade com base no rendimento (pacotes × unidades)
- Carrinho rápido com revisão antes de confirmar
- Fechamento de pedido com confirmação no WhatsApp **ou** registro direto no sistema

### 5.3 Arquitetura de Rotas — Portal do Cliente

```
/loja                   → Catálogo de Produtos (home do portal)
/loja/produto/{id}      → Detalhe do Produto (opcional, fase futura)
/loja/carrinho          → Carrinho e Revisão
/loja/pedidos           → Histórico de Pedidos do cliente logado
/loja/pedidos/{id}      → Detalhe de um pedido
```

**Todas as rotas `/loja/*` exigem sessão com `tipo_usuario = CLIENTE`.**

### 5.4 Interface — Catálogo Visual (/loja)

**Conceito de Design:** "Cardápio Premium" — foco em foto do produto, nome comercial e preço claro. Sem dados técnicos (sem custo de produção, sem FC, sem margem).

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│  SmartFood — Portal de Compras          👤 Boteco do Zé  ↗  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Olá, Boteco do Zé! 👋  Faça seu pedido de reposição.      │
│                                                             │
│  [🔍 Buscar produto...]          Filtro: [Todos ▼]          │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │  📸 FOTO     │ │  📸 FOTO     │ │  📸 FOTO     │        │
│  │              │ │              │ │              │        │
│  │ Coxinha de   │ │ Bolinha de   │ │ Kibe Frito   │        │
│  │ Frango       │ │ Queijo       │ │              │        │
│  │              │ │              │ │              │        │
│  │ Pct 50 un.   │ │ Pct 30 un.  │ │ Pct 40 un.  │        │
│  │ R$ 47,90     │ │ R$ 38,50    │ │ R$ 42,00    │        │
│  │              │ │              │ │              │        │
│  │ [ − ] [ 2 ] [ + ] → 🛒       │ ...                     │
│  └──────────────┘ ...                                       │
│                                                             │
│  ┌─────────────────────────────────────────┐               │
│  │  🛒  Carrinho: 3 itens · R$ 148,30      │               │
│  │  [ Revisar e Confirmar Pedido → ]       │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

**Especificações do Card de Produto:**

| Campo | Fonte de Dados | Visibilidade |
|---|---|---|
| Foto do Produto | `Recipe.foto_url` (campo novo) | Sempre |
| Nome Comercial | `Recipe.nome_comercial` (campo novo, fallback: `Recipe.name`) | Sempre |
| Unidade de Venda | `Recipe.rendimento_unidades` + `Recipe.unidade_venda` | Sempre |
| Preço | `PriceTable` vinculada ao `Customer` ou preço sugerido da ficha | Sempre |
| Estoque Disponível | `Recipe.current_stock_units` | Apenas se > 0 (badge "Em Estoque") |
| Custo de Produção | `Recipe.total_cost` | **NUNCA visível ao cliente** |

**Interação de Quantidade:**

```
[ − ]  [ 2 pacotes ]  [ + ]
            ↓
      = 100 unidades
```

O sistema calcula: `quantidade_display = pacotes × rendimento_unidades`

**Seletor de Quantidade:** Apenas incrementos inteiros de "pacotes" (não frações). O sistema bloqueia quantidade além do estoque disponível com mensagem amigável: *"Disponível: 3 pacotes. Fale conosco para pedir mais."*

### 5.5 Interface — Catálogo (Detalhe Mobile)

No mobile (< 640px), o layout muda para lista vertical com foto à esquerda:

```
┌─────────────────────────────────────────┐
│  📸  Coxinha de Frango                  │
│       Pct 50 un. · R$ 47,90            │
│       [ − ]  [ 2 ]  [ + ]  🛒          │
├─────────────────────────────────────────┤
│  📸  Bolinha de Queijo                  │
│       Pct 30 un. · R$ 38,50            │
│       [ − ]  [ 0 ]  [ + ]  🛒          │
└─────────────────────────────────────────┘
```

### 5.6 Interface — Carrinho (/loja/carrinho)

```
┌─────────────────────────────────────────────────────────────┐
│  ← Voltar ao Catálogo       🛒 Seu Pedido                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Coxinha de Frango          2 pct × R$ 47,90 = R$ 95,80   │
│  Bolinha de Queijo          1 pct × R$ 38,50 = R$ 38,50   │
│                                                             │
│  ─────────────────────────────────────────────────────────  │
│  Subtotal                                        R$ 134,30  │
│                                                             │
│  📝 Observações para este pedido:                           │
│  [                                              ]           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✅  CONFIRMAR PEDIDO                               │   │
│  │      Registra no sistema e notifica a produção      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  OU                                                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📱  Enviar via WhatsApp                            │   │
│  │      Abre o WhatsApp com o pedido formatado         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Lógica do Botão WhatsApp:**

O número de WhatsApp é configurado na empresa (campo novo `Company.whatsapp_contato`). A mensagem gerada:

```
Olá! Sou *Boteco do Zé*.
Gostaria de fazer o seguinte pedido:

• 2 pacotes de Coxinha de Frango (100 un.)
• 1 pacote de Bolinha de Queijo (30 un.)

*Total estimado: R$ 134,30*

Aguardo confirmação. Obrigado!
```

**Lógica do Botão "Confirmar Pedido":**

- Cria um `SalesOrder` com `status = "PENDING"` via POST `/orders` (endpoint existente).
- Exibe confirmação: *"Pedido #42 registrado! Em breve entraremos em contato."*
- Limpa o carrinho (localStorage / Alpine.js state).

### 5.7 Interface — Histórico de Pedidos (/loja/pedidos)

```
┌─────────────────────────────────────────────────────────────┐
│  Meus Pedidos                              ← Ir às Compras  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  📦 Pedido #42 — 15/05/2026                                 │
│  Coxinha de Frango (2 pct), Bolinha de Queijo (1 pct)       │
│  R$ 134,30             [ 🕐 Pendente ]      [ Ver → ]       │
│                                                             │
│  📦 Pedido #38 — 02/05/2026                                 │
│  Kibe Frito (3 pct)                                         │
│  R$ 126,00             [ ✅ Entregue ]      [ Ver → ]       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.8 Campos Novos Necessários nos Modelos

**Tabela `recipes` — novos campos via ALTER TABLE:**

```sql
ALTER TABLE recipes ADD COLUMN nome_comercial TEXT DEFAULT '';
ALTER TABLE recipes ADD COLUMN foto_url       TEXT DEFAULT '';
ALTER TABLE recipes ADD COLUMN descricao_venda TEXT DEFAULT '';
ALTER TABLE recipes ADD COLUMN unidade_venda  TEXT DEFAULT 'pacote';
ALTER TABLE recipes ADD COLUMN visivel_loja   INTEGER DEFAULT 0;
```

**Nova tabela `price_tables`:**

```sql
CREATE TABLE price_tables (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    recipe_id   INTEGER NOT NULL REFERENCES recipes(id),
    preco       REAL    NOT NULL,
    criado_em   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, recipe_id)
);
```

**Nova tabela `company_config`:**

```sql
CREATE TABLE company_config (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    whatsapp_contato TEXT DEFAULT '',
    nome_fantasia   TEXT DEFAULT 'SmartFood',
    logo_url        TEXT DEFAULT ''
);
```

### 5.9 Painel Admin — Gerenciar Catálogo da Loja

**URL:** `/admin/loja`  
**Acesso:** Apenas ADMIN / PRODUCAO

Permite ao admin:
- Marcar/desmarcar produtos como visíveis na loja (`visivel_loja = 1`)
- Definir `nome_comercial`, `descricao_venda`, `foto_url`
- Definir preço especial por cliente (tabela de preços)

```
┌─────────────────────────────────────────────────────────────┐
│  Configurar Catálogo da Loja                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Coxinha de Frango        [✅ Visível na Loja]              │
│  Nome comercial:  [Coxinha Artesanal de Frango     ]        │
│  Descrição:       [Frango desfiado com temperos    ]        │
│  URL da Foto:     [https://...                     ]        │
│  Preço padrão:    R$ [47,90]                                │
│                                                             │
│  Preços por Cliente:                                        │
│  Boteco do Zé:         R$ [45,00]    (−6%)                 │
│  Bar do Carlinhos:     R$ [47,90]    (padrão)              │
│                                                             │
│  [💾 Salvar]                                               │
└─────────────────────────────────────────────────────────────┘
```

### 5.10 Rotas Backend — Etapa B

| Método | URL | Função | Acesso |
|---|---|---|---|
| GET | `/loja` | Catálogo de produtos | CLIENTE |
| GET | `/loja/carrinho` | Página do carrinho | CLIENTE |
| GET | `/loja/pedidos` | Histórico de pedidos do cliente | CLIENTE |
| GET | `/loja/pedidos/{id}` | Detalhe de um pedido | CLIENTE |
| POST | `/loja/orders` | Criar pedido (wrapper do /orders existente) | CLIENTE |
| GET | `/admin/loja` | Painel de gerenciamento do catálogo | ADMIN/PRODUCAO |
| POST | `/admin/loja/produto/{id}` | Atualizar configurações do produto na loja | ADMIN/PRODUCAO |
| POST | `/admin/loja/preco` | Definir preço por cliente | ADMIN/PRODUCAO |

---

## 6. Etapa C — Guia do Produto via QR Code

### 6.1 Conceito

Quando a embalagem do produto sai da fábrica com o QR Code impresso, esse QR redireciona hoje para uma URL externa (`tutorial_url` ou `promo_url`). Na v3.0, o sistema gera uma **página própria e rica**, hospedada no SmartFood, sem necessidade de login, que serve como o "manual de uso" do produto para o cliente B2B.

### 6.2 Fluxo de Acesso

```
QR Code na Embalagem
        ↓
  GET /qr/{batch_id}   ← Endpoint existente (mantido)
        ↓
  resolve_qr_url()     ← Função existente em label_service.py
        ↓
  Se tutorial_url = "/produto/{batch_id}" (URL interna)
        ↓
  GET /produto/{batch_id}  ← NOVA ROTA PÚBLICA (sem login)
        ↓
  Guia do Produto (HTML responsivo, mobile-first)
```

**Integração com o fluxo existente:** O admin, ao registrar o lote em `/labels`, preenche o campo `tutorial_url` com `/produto/{batch_id}` (ou o sistema preenche automaticamente ao finalizar produção).

### 6.3 URL Pública

```
GET /produto/{batch_id}
```

**Totalmente pública — sem autenticação.** Renderiza uma página HTML standalone (sem `base.html`, sem sidebar, sem dados internos).

### 6.4 Interface — Guia do Produto

**Design:** "Revista Gastronômica Digital" — visual premium, mobile-first, imersivo.

```
╔═════════════════════════════════════╗
║   🍗                                ║
║   Coxinha Artesanal                 ║
║   de Frango Defumado                ║
║                                     ║
║   ✓ Fresco · Lote L-20240515-042   ║
║   Válido até: 18/06/2026            ║
╠═════════════════════════════════════╣
║                                     ║
║   🔥 MODO DE PREPARO               ║
║   ─────────────────────────────    ║
║   Fritar em óleo a 175°C           ║
║   por 4 a 6 minutos                ║
║                                     ║
║   OU                                ║
║                                     ║
║   Forno combinado: 180°C           ║
║   por 8 minutos                     ║
║                                     ║
║   ⚠️ Não descongele antes          ║
║   de fritar. Frite direto.         ║
║                                     ║
╠═════════════════════════════════════╣
║                                     ║
║   🍽️ COMO SERVIR                   ║
║   ─────────────────────────────    ║
║   ┌─────────┐ ┌─────────┐         ║
║   │  📸     │ │  📸     │         ║
║   │  foto 1 │ │  foto 2 │         ║
║   └─────────┘ └─────────┘         ║
║                                     ║
║   • Sirva em tábua de madeira      ║
║   • Acompanhe com geleia de        ║
║     pimenta ou maionese defumada   ║
║   • Decore com cebolinha picada    ║
║                                     ║
╠═════════════════════════════════════╣
║                                     ║
║   📝 NOMES PARA SEU CARDÁPIO       ║
║   ─────────────────────────────    ║
║                                     ║
║   [COPIAR] Coxinha Artesanal de    ║
║            Frango Defumado         ║
║                                     ║
║   [COPIAR] Coxinha da Casa com     ║
║            Frango Caipira          ║
║                                     ║
║   [COPIAR] Coxinhão Defumado       ║
║            Especial                ║
║                                     ║
╠═════════════════════════════════════╣
║                                     ║
║   🔎 RASTREABILIDADE               ║
║   ─────────────────────────────    ║
║   Lote: L-20240515-042             ║
║   Produzido em: 15/05/2026         ║
║   Validade: 18/06/2026             ║
║   Ingredientes: Frango, Farinha,   ║
║   Requeijão, Temperos Naturais     ║
║                                     ║
║   ─────────────────────────────    ║
║   Fabricado por SmartFood          ║
║   CNPJ: XX.XXX.XXX/0001-XX        ║
║                                     ║
╚═════════════════════════════════════╝
```

### 6.5 Seções da Página — Especificação Detalhada

#### Seção 1: Hero — Identificação do Produto

| Campo | Fonte de Dados | Obrigatoriedade |
|---|---|---|
| Nome Comercial | `Recipe.nome_comercial` → fallback `ProductionBatch.product_name` | Obrigatório |
| Foto principal | `Recipe.foto_url` | Opcional (placeholder se ausente) |
| Número do Lote | `ProductionBatch.batch_number` | Obrigatório |
| Data de Validade | `ProductionBatch.expiry_date` | Obrigatório |
| Badge de Frescor | Calculado: dias restantes. Verde ≥ 7 dias, Amarelo < 7, Vermelho vencido | Automático |

#### Seção 2: Modo de Preparo Industrial

| Campo | Fonte de Dados |
|---|---|
| Instruções de Preparo | `RecipeSection.instrucoes` da seção marcada como "modo_preparo_interno" |
| Temperatura e Tempo | Extraído do texto de instrucoes com destaque visual |
| Alertas de Segurança | Campo novo: `Recipe.alertas_preparo` (ex: "Não descongele antes de fritar") |

**Design especial:** Temperatura e tempo são exibidos em destaque grande e monospace, como display de forno industrial.

#### Seção 3: Dicas de Apresentação

| Campo | Fonte de Dados |
|---|---|
| Galeria de Fotos | `Recipe.fotos_apresentacao` — JSON array de URLs (campo novo) |
| Dicas Textuais | `Recipe.dicas_apresentacao` (campo novo, texto markdown simples) |

A galeria usa scroll horizontal no mobile e grid 2 colunas no desktop.

#### Seção 4: Sugestões de Nomes para Cardápio

| Campo | Fonte de Dados |
|---|---|
| Lista de Nomes Sugeridos | `Recipe.nomes_cardapio` — JSON array de strings (campo novo) |

Cada nome tem um botão **[Copiar]** que usa `navigator.clipboard.writeText()` — sem backend.

#### Seção 5: Rastreabilidade

| Campo | Fonte de Dados |
|---|---|
| Número do Lote | `ProductionBatch.batch_number` |
| Data de Produção | `ProductionBatch.production_date` |
| Data de Validade | `ProductionBatch.expiry_date` |
| Lista de Ingredientes | `ProductionBatch.ingredients_summary` |
| Fabricante | `CompanyConfig.nome_fantasia` + CNPJ |

### 6.6 Novos Campos em `recipes` — Etapa C

```sql
ALTER TABLE recipes ADD COLUMN fotos_apresentacao TEXT DEFAULT '[]';
-- JSON array: ["https://url1.jpg", "https://url2.jpg"]

ALTER TABLE recipes ADD COLUMN dicas_apresentacao TEXT DEFAULT '';
-- Texto livre com dicas de como servir

ALTER TABLE recipes ADD COLUMN nomes_cardapio TEXT DEFAULT '[]';
-- JSON array: ["Coxinha Artesanal de Frango", "Coxinha da Casa"]

ALTER TABLE recipes ADD COLUMN alertas_preparo TEXT DEFAULT '';
-- Alertas de segurança alimentar no preparo
```

### 6.7 Integração com Geração de Lote

Ao finalizar produção em `/producao` (módulo existente), o sistema preenche automaticamente o campo `tutorial_url` com `/produto/{batch_id}`, eliminando a necessidade de o usuário digitar a URL.

**Código a adicionar em `main.py` na rota POST `/batches`:**

```python
# Após criar o batch e obter batch.id:
if not tutorial_url:
    batch.tutorial_url = f"/produto/{batch.id}"
```

### 6.8 Painel Admin — Enriquecer Produto para QR Code

**URL:** `/admin/loja` (mesma tela da Etapa B, nova aba "QR Code / Guia do Produto")**

```
┌─────────────────────────────────────────────────────────────┐
│  [Aba: Catálogo Loja]  [Aba: Guia QR Code ←]               │
├─────────────────────────────────────────────────────────────┤
│  Produto: Coxinha de Frango                                 │
│                                                             │
│  Fotos de Apresentação (URLs, uma por linha):               │
│  [https://...foto1.jpg                              ]       │
│  [https://...foto2.jpg                              ]       │
│  [+ Adicionar foto]                                         │
│                                                             │
│  Dicas de Apresentação:                                     │
│  [ Sirva em tábua de madeira com geleia de pimenta...]      │
│                                                             │
│  Nomes para Cardápio (um por linha):                        │
│  [ Coxinha Artesanal de Frango Defumado             ]       │
│  [ Coxinha da Casa com Frango Caipira               ]       │
│  [+ Adicionar nome]                                         │
│                                                             │
│  Alertas de Preparo:                                        │
│  [ Não descongele antes de fritar. Frite direto.    ]       │
│                                                             │
│  [💾 Salvar]   [👁️ Prévia do Guia →]                       │
└─────────────────────────────────────────────────────────────┘
```

O botão "Prévia do Guia" abre `/produto/{recipe_id}?preview=1` — mostrando como ficará o guia com dados de exemplo (sem batch real).

### 6.9 Rotas Backend — Etapa C

| Método | URL | Função | Acesso |
|---|---|---|---|
| GET | `/produto/{batch_id}` | Guia público do produto | Público (sem login) |
| GET | `/produto/{batch_id}?preview=1` | Preview admin (usa dados de exemplo) | ADMIN/PRODUCAO |

---

## 7. Requisitos de Design

### 7.1 Sistema de Design Interno (ERP)

Mantém o design atual (`base.html`) sem alterações. A única adição é o link de logout e o nome do usuário no header.

### 7.2 Sistema de Design — Portal do Cliente (/loja)

**Filosofia:** "Clean B2B Commerce" — focado em conversão, sem distrações.

| Token | Valor |
|---|---|
| Fundo | `#f8fafc` (slate-50) |
| Card Produto | `#ffffff` com sombra sutil `0 1px 3px rgba(0,0,0,.1)` |
| Cor Primária | `#16a34a` (green-600) — reforça frescor/naturalidade |
| Cor Secundária | `#1e40af` (blue-800) |
| Fonte Títulos | Outfit, sans-serif |
| Fonte Corpo | Inter, sans-serif |
| Botão Mínimo | 48px de altura |
| Breakpoint Mobile | 640px |

**O Portal do Cliente NÃO usa `base.html`** — tem seu próprio layout sem sidebar do ERP.

### 7.3 Sistema de Design — Guia do Produto QR (/produto)

**Filosofia:** "Revista Gastronômica" — visual premium, imersivo, mobile-first.

| Token | Valor |
|---|---|
| Fundo | `#0f172a` (slate-900) — escuro, premium |
| Card Seções | `#1e293b` (slate-800) |
| Acento Principal | `#f59e0b` (amber-500) — quente, apetitoso |
| Acento Temperatura | `#ef4444` (red-500) — destaque de segurança |
| Fonte Títulos | Playfair Display, serif — editorial, gastronômico |
| Fonte Dados Técnicos | JetBrains Mono, monospace — temperatura, tempo, lote |
| Fonte Corpo | Inter, sans-serif |
| Botão Mínimo | 48px de altura |
| Layout | 100% mobile-first, max-width 480px, centralizado |
| Animação | Fade-in suave nas seções ao rolar (Intersection Observer) |

### 7.4 Tela de Login

**Filosofia:** "Industrial Minimal" — coerente com o restante do ERP.

| Token | Valor |
|---|---|
| Fundo | `#f1f5f9` (slate-100) com grid de pontos sutil |
| Card | `#ffffff` com border-radius 1rem e sombra `0 20px 60px rgba(0,0,0,.12)` |
| Acento | `#2563eb` (blue-600) |
| Fonte | Inter, sans-serif |

### 7.5 Requisitos Universais de Acessibilidade

- Todos os botões interativos: mínimo 48px de altura e 44px de largura.
- Contraste mínimo: 4.5:1 (WCAG AA).
- Campos de formulário: labels visíveis (não apenas placeholder).
- Mensagens de erro: associadas ao campo via `aria-describedby`.
- Foco visível em todos os elementos interativos.

---

## 8. Especificação Técnica

### 8.1 Dependências Novas

```
# requirements.txt — adicionar
passlib[bcrypt]       # hash de senha seguro
starlette[full]       # SessionMiddleware (já incluso com fastapi[all])
python-jose[cryptography]  # (opcional, para JWT futuro)
```

### 8.2 Configuração do SessionMiddleware

```python
# main.py — adicionar após criar o app FastAPI
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key="TROQUE_ISSO_POR_UMA_CHAVE_SEGURA_DE_32_CHARS",
    max_age=86400,         # 24 horas
    same_site="lax",
    https_only=False,      # True em produção com HTTPS
)
```

**A secret_key deve vir de uma variável de ambiente em produção.**

### 8.3 Hash de Senha

```python
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)

def verificar_senha(senha: str, hash: str) -> bool:
    return pwd_context.verify(senha, hash)
```

### 8.4 Motor de QR — Integração com /produto

```python
# Em label_service.py — atualizar resolve_qr_url para suportar URL interna
def resolve_qr_url(expiry_date, tutorial_url, promo_url, batch_id=None):
    now = datetime.utcnow()
    cutoff = expiry_date - timedelta(days=PROMO_DAYS_BEFORE_EXPIRY)
    use_promo = (now >= cutoff) and bool(promo_url)
    
    if use_promo:
        return promo_url
    
    # Se não há tutorial_url externa, usa a interna
    if not tutorial_url and batch_id:
        return f"/produto/{batch_id}"
    
    return tutorial_url or "/"
```

### 8.5 Performance — Página /produto/{batch_id}

**Requisito:** Carregamento < 1 segundo.

Estratégias:
- Página renderizada no servidor (SSR via Jinja2) — zero JS blocking.
- Imagens com `loading="lazy"` e `width`/`height` declarados.
- CSS inline crítico no `<head>` — sem bloqueio de render.
- Alpine.js carregado com `defer` — apenas para o botão "Copiar".
- Sem chamadas de API após o carregamento inicial.
- Cache de 60 segundos via header `Cache-Control: public, max-age=60`.

### 8.6 Segurança — Isolamento de Dados do Cliente

**Regra fundamental:** Um usuário tipo `CLIENTE` nunca pode acessar dados de outro cliente.

```python
# Dependency para verificar propriedade
async def get_current_customer(request: Request, db: Session = Depends(get_db)):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        raise HTTPException(403)
    customer = db.query(models.Customer).filter_by(id=cliente_id).first()
    if not customer:
        raise HTTPException(404)
    return customer

# Uso em rota de pedidos:
@app.get("/loja/pedidos")
async def loja_pedidos(
    request: Request,
    customer: Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    # Filtra SEMPRE pelo customer da sessão — nunca aceita customer_id da URL
    orders = db.query(SalesOrder).filter_by(customer_id=customer.id).all()
```

### 8.7 Migrations Idempotentes

Todos os novos campos são adicionados via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` no padrão já adotado no sistema (`_MIGRATIONS` list em `main.py`):

```python
_MIGRATIONS = [
    # ... migrações existentes ...
    
    # v3.0 — Usuários
    "ALTER TABLE recipes ADD COLUMN nome_comercial TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN foto_url TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN descricao_venda TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN unidade_venda TEXT DEFAULT 'pacote'",
    "ALTER TABLE recipes ADD COLUMN visivel_loja INTEGER DEFAULT 0",
    "ALTER TABLE recipes ADD COLUMN fotos_apresentacao TEXT DEFAULT '[]'",
    "ALTER TABLE recipes ADD COLUMN dicas_apresentacao TEXT DEFAULT ''",
    "ALTER TABLE recipes ADD COLUMN nomes_cardapio TEXT DEFAULT '[]'",
    "ALTER TABLE recipes ADD COLUMN alertas_preparo TEXT DEFAULT ''",
]
```

As tabelas `users`, `price_tables` e `company_config` são criadas via `Base.metadata.create_all()` (automático ao adicionar as classes em `models.py`).

### 8.8 Dados de Seed — Primeiro Usuário Admin

```python
# seed_admin.py — executar uma vez após ativar Etapa A
from database import SessionLocal
from models import User
from main import hash_senha

def seed_admin():
    db = SessionLocal()
    admin = db.query(User).filter_by(email="admin@smartfood.com").first()
    if not admin:
        db.add(User(
            nome="Administrador",
            email="admin@smartfood.com",
            senha_hash=hash_senha("smartfood2026"),
            tipo_usuario="ADMIN",
        ))
        db.commit()
        print("Admin criado: admin@smartfood.com / smartfood2026")
    db.close()

if __name__ == "__main__":
    seed_admin()
```

---

## 9. Critérios de Aceite

### Etapa A — Gestão de Usuários

| # | Cenário | Resultado Esperado |
|---|---|---|
| A1 | Acessar `/dashboard` sem sessão | Redirect para `/login` |
| A2 | Login com e-mail e senha corretos (ADMIN) | Redirect para `/dashboard`, nome do usuário no header |
| A3 | Login com e-mail e senha corretos (CLIENTE) | Redirect para `/loja` |
| A4 | Login com senha incorreta | Mensagem de erro inline; sem redirect |
| A5 | Admin cria usuário tipo CLIENTE sem cliente vinculado | Erro de validação: "Selecione o cliente" |
| A6 | Admin reseta senha de usuário | Nova senha temporária exibida; usuário consegue logar com ela |
| A7 | Admin desativa usuário | Usuário desativado não consegue logar (mensagem: "Conta inativa") |
| A8 | Usuário CLIENTE tenta acessar `/dashboard` | HTTP 403 / redirect para `/loja` |
| A9 | Usuário PRODUCAO tenta acessar `/admin/usuarios` | HTTP 403 |
| A10 | GET `/logout` | Sessão encerrada, redirect para `/login` |

### Etapa B — Portal do Cliente B2B

| # | Cenário | Resultado Esperado |
|---|---|---|
| B1 | Cliente acessa `/loja` | Catálogo com produtos marcados como `visivel_loja = 1` |
| B2 | Cliente vê preço | Preço da `price_table` do cliente; fallback para preço padrão |
| B3 | Cliente adiciona 2 pacotes ao carrinho | Subtotal calculado corretamente |
| B4 | Cliente tenta pedir além do estoque | Quantidade bloqueada com mensagem amigável |
| B5 | Cliente confirma pedido | `SalesOrder` criado com `customer_id` da sessão, status PENDING |
| B6 | Cliente clica "WhatsApp" | Link abre com mensagem formatada, número correto da empresa |
| B7 | Cliente acessa histórico | Apenas pedidos do próprio cliente (nunca de outros) |
| B8 | Cliente tenta acessar `/dashboard` | HTTP 403, redirect para `/loja` |
| B9 | Admin marca produto como visível | Produto aparece imediatamente no `/loja` |
| B10 | Admin define preço especial para cliente X | Cliente X vê preço especial; outros veem preço padrão |

### Etapa C — Guia do Produto QR Code

| # | Cenário | Resultado Esperado |
|---|---|---|
| C1 | Acessar `/produto/{id}` sem login | Página carrega normalmente (sem redirect para login) |
| C2 | Produto com validade futura | Badge verde "Válido por N dias" |
| C3 | Produto com validade em 2 dias | Badge vermelho "Vence em 2 dias" |
| C4 | Produto com `fotos_apresentacao` preenchido | Galeria de fotos exibida na seção "Como Servir" |
| C5 | Produto sem fotos | Placeholder elegante (sem erro) |
| C6 | Botão "Copiar" em nome de cardápio | Texto copiado para clipboard; feedback visual "Copiado!" |
| C7 | Página em mobile (375px) | Layout 100% funcional, sem scroll horizontal, botões ≥ 48px |
| C8 | Tempo de carregamento | < 1 segundo em conexão 4G simulada (Lighthouse) |
| C9 | `/produto/{id}` com batch inexistente | HTTP 404 com página amigável |
| C10 | Finalizar produção em `/producao` | `ProductionBatch.tutorial_url` preenchido automaticamente com `/produto/{id}` |
| C11 | `/qr/{id}` aponta para `/produto/{id}` internamente | Redirect funciona corretamente |
| C12 | `nomes_cardapio` com 3 sugestões | 3 botões "Copiar" exibidos corretamente |

---

## 10. Plano de Implementação

### Sequência Recomendada

```
SEMANA 1 — Etapa A (Gestão de Usuários)
├── Dia 1:  Criar modelo User em models.py
│           Adicionar SessionMiddleware em main.py
│           Criar seed_admin.py
├── Dia 2:  Criar templates/login.html
│           Implementar POST /login com verificação de senha
│           Implementar GET /logout
├── Dia 3:  Criar templates/admin/usuarios.html
│           Implementar rotas CRUD /admin/usuarios/*
│           Adicionar proteção de rotas (dependencies)
├── Dia 4:  Atualizar base.html (logout, nome do usuário)
│           Testar todos os cenários A1–A10
└── Dia 5:  Ajustes, correções, documentação

SEMANA 2 — Etapa B (Portal do Cliente)
├── Dia 1:  Aplicar ALTER TABLEs em recipes, criar price_tables
│           Criar templates/loja/base_loja.html (layout sem sidebar)
│           Implementar GET /loja (catálogo)
├── Dia 2:  Criar templates/loja/catalogo.html
│           Criar templates/loja/carrinho.html
├── Dia 3:  Implementar lógica de carrinho (Alpine.js)
│           Implementar POST /loja/orders
│           Implementar link WhatsApp
├── Dia 4:  Criar templates/loja/pedidos.html
│           Implementar GET /loja/pedidos
│           Criar templates/admin/loja.html
├── Dia 5:  Implementar rotas /admin/loja
│           Testar cenários B1–B10

SEMANA 3 — Etapa C (Guia do Produto QR)
├── Dia 1:  Aplicar ALTER TABLEs de fotos, dicas, nomes, alertas
│           Criar templates/public/produto.html
│           Implementar GET /produto/{batch_id}
├── Dia 2:  Design e CSS da página produto (mobile-first)
│           Implementar seções Hero, Preparo, Apresentação
├── Dia 3:  Implementar seção Nomes + botão Copiar
│           Implementar seção Rastreabilidade
│           Integrar com fluxo de finalização em /producao
├── Dia 4:  Adicionar aba QR Code em /admin/loja
│           Implementar preview admin do guia
├── Dia 5:  Teste de performance (Lighthouse)
│           Teste mobile completo
│           Ajustes finais + documentação
```

### Rollback

- **Etapa A:** Remover `SessionMiddleware` e dependências de autenticação das rotas. O sistema volta a ser acessível sem login. Os dados de `users` ficam na tabela mas não são usados.
- **Etapa B:** Remover rotas `/loja/*`. As tabelas `price_tables` e campos novos em `recipes` ficam sem uso mas não causam dano.
- **Etapa C:** Remover rota `/produto/*`. A `tutorial_url` pode apontar para URL externa como antes.

---

## 11. Impacto Técnico Consolidado

| Item | Etapa A | Etapa B | Etapa C | Total |
|---|---|---|---|---|
| Arquivos novos | 3 templates | 5 templates | 2 templates | 10 |
| Arquivos alterados | 3 (models, main, base.html) | 2 (models, main) | 2 (main, label_service) | 4 únicos |
| Novas tabelas | 1 (users) | 2 (price_tables, company_config) | 0 | 3 |
| Campos novos em recipes | 0 | 5 | 4 | 9 |
| Novas rotas | 8 | 9 | 2 | 19 |
| Rotas alteradas | 0 | 0 | 1 (/batches — auto-preencher tutorial_url) | 1 |
| Migrations | 0 destrutivas | 0 destrutivas | 0 destrutivas | 0 |
| Testes de aceite | 10 | 10 | 12 | 32 |

---

## 12. Dependências e Pré-condições

| Condição | Responsável | Observação |
|---|---|---|
| Executar `seed_admin.py` após ativar Etapa A | Desenvolvedor | Cria o primeiro usuário ADMIN |
| Clientes já devem estar cadastrados em `/clientes` antes de criar usuários tipo CLIENTE | Operador | Use clientes existentes |
| Produtos devem ter `visivel_loja = 1` para aparecer no portal | Admin | Configurar em `/admin/loja` |
| Fotos de produtos devem estar hospedadas em URL acessível (CDN ou servidor de mídia) | Admin | Na v3.0, apenas URLs externas; upload de arquivo é fase futura |
| `CompanyConfig.whatsapp_contato` deve estar preenchido para o botão WhatsApp funcionar | Admin | Configurar em `/admin/loja` ou nova tela de configurações |
| `SECRET_KEY` do SessionMiddleware deve ser uma string aleatória de 32+ caracteres | Desenvolvedor | Usar variável de ambiente em produção |
| `passlib[bcrypt]` instalado (`pip install passlib[bcrypt]`) | Desenvolvedor | Adicionar ao requirements.txt |
| Python 3.13 + FastAPI 0.128 (já atendidos) | — | Já instalados |
| `segno` instalado (já está em requirements.txt) | — | Sem alteração |

---

*Fim do documento PRD — SmartFood Ops 360 v3.0*  
*Próxima revisão: após conclusão da Etapa A.*
