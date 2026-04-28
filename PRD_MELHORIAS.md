Este PRD (Documento de Requisitos do Produto) detalha a implementação da funcionalidade de atalho para vinculação direta de produtos ao catálogo a partir do cartão do fornecedor, otimizando o fluxo de cadastro no **SmartFood Ops 360**.

---

# 📋 PRD: Atalho de Vinculação Direta ao Catálogo

## 1. Visão Geral
Atualmente, para vincular um insumo a um fornecedor, o usuário deve rolar manualmente até a seção "Catálogo de Compras" no final da página de Cadastros e selecionar o fornecedor no menu suspenso. Esta melhoria introduz um botão de ação direta em cada cartão de fornecedor que automatiza esse processo, melhorando a descoberta da funcionalidade e a velocidade de operação.

## 2. Objetivos
* **Aumentar a usabilidade:** Tornar óbvia a relação entre Fornecedores e Catálogo.
* **Reduzir cliques:** Eliminar a necessidade de busca manual do fornecedor no formulário de catálogo.
* **Melhorar o fluxo:** Permitir que o usuário, ao cadastrar um novo fornecedor, já inicie a montagem de seu catálogo imediatamente.

## 3. Histórias de Usuário
| Como... | Eu quero... | Para que... |
| :--- | :--- | :--- |
| Comprador | Ter um botão "+ Adicionar ao Catálogo" no cartão do fornecedor | Eu possa vincular insumos a ele sem precisar procurá-lo novamente em uma lista longa. |
| Operador | Que a tela role automaticamente para o formulário | Eu tenha certeza de que a ação foi iniciada e saiba onde preencher os dados. |

## 4. Requisitos Funcionais

### RF01: Botão de Ação no Cartão
Cada item na lista de fornecedores (`#suppliers-list`) deve conter um botão primário ou secundário com o texto ou ícone de "+ Catálogo".

### RF02: Preenchimento Automático (Auto-fill)
Ao clicar no botão, o valor do `supplier_id` no formulário de catálogo (`#catalog-form`) deve ser alterado automaticamente para o ID do fornecedor correspondente ao cartão clicado.

### RF03: Rolagem Suave (Smooth Scroll)
O sistema deve realizar uma rolagem suave da página até a seção de cadastro de catálogo para manter o contexto visual do usuário.

## 5. Requisitos de Design (UI/UX)
* **Localização:** O botão deve ficar posicionado próximo aos botões de Editar/Excluir no modo de visualização do fornecedor.
* **Estilo:** Seguir o padrão de botões secundários do sistema para não competir visualmente com a ação de "Salvar" principal.
* **Feedback:** O campo de fornecedor no formulário de destino pode piscar brevemente ou ser destacado para confirmar o preenchimento.

---

## 6. Especificação Técnica (Implementação Sugerida)

### A. Alteração no Template (`templates/index.html`)
No loop de fornecedores, adicione o botão com uma chamada Alpine.js:

```html
<div class="flex gap-1 flex-shrink-0">
  <button @click="fillCatalogSupplier('{{ s.id }}')" 
          class="icon-btn text-blue-400 hover:bg-blue-900/20" 
          title="Vincular produto a este fornecedor">
    ➕
  </button>
  
  <button @click="editing=true" class="icon-btn hover:text-blue-400">✏️</button>
  </div>
```

### B. Lógica Alpine.js (`templates/index.html` ou `app.js`)
Adicione a função auxiliar ao escopo do `crudApp()`:

```javascript
function crudApp() {
  return {
    // ... funções existentes ...

    fillCatalogSupplier(supplierId) {
      // 1. Encontra o select de fornecedor no formulário de catálogo
      const catalogSelect = document.querySelector('select[name="supplier_id"]');
      
      if (catalogSelect) {
        // 2. Preenche o valor
        catalogSelect.value = supplierId;
        
        // 3. Rola até a seção (usando o cabeçalho do catálogo como âncora)
        const catalogSection = document.getElementById('catalog-body').closest('.section-card');
        catalogSection.scrollIntoView({ behavior: 'smooth' });
        
        // 4. Feedback visual opcional: focar no próximo campo (Ingrediente)
        setTimeout(() => {
          document.querySelector('select[name="ingredient_id"]').focus();
          toast('Fornecedor selecionado no catálogo');
        }, 500);
      }
    }
  };
}
```

## 7. Critérios de Aceite
1. O botão deve estar visível em todos os fornecedores listados.
2. Clicar no botão de "Fornecedor A" deve selecionar o "Fornecedor A" no formulário de catálogo.
3. A página deve rolar até o formulário sem recarregar (SPA feel).
4. O funcionamento não deve interferir na capacidade de selecionar fornecedores manualmente no formulário.

## 8. Melhorias Futuras Relacionadas
* **Badge de Contagem:** Mostrar no cartão do fornecedor quantos itens ele já possui no catálogo.
* **Filtro Rápido:** Ao clicar no nome de um fornecedor, filtrar a tabela de catálogo abaixo para mostrar apenas os itens dele.