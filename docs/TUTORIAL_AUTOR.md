# Tutorial do Autor — Sistema SRA (Relatórios D20)

## Visão Geral do Processo

Como **autor** do relatório mensal D20, você é responsável por preencher o conteúdo de uma ou mais seções específicas. O sistema SRA automatiza a compilação, formatação e geração do PDF final no padrão visual Concremat/PLI-SP.

**Seu trabalho:** enviar apenas o conteúdo (texto, figuras, tabelas) da sua seção. O sistema cuida do resto.

---

## 1. Acesso ao Sistema

### 1.1. Recebimento das Credenciais

Você receberá um e-mail do coordenador contendo:
- **E-mail de login** (seu e-mail corporativo)
- **Senha inicial** (temporária)
- **Link do sistema:** `https://sra-pli-starter.onrender.com`

### 1.2. Primeiro Acesso

1. Acesse o link fornecido
2. Na tela de login, preencha:
   - **E-mail:** seu e-mail corporativo
   - **Perfil:** selecione `Autor`
   - **Senha:** a senha temporária recebida

3. Clique em **Entrar**

> **Dica:** Se esqueceu a senha, clique em "Esqueci minha senha" e siga as instruções.

---

## 2. Interface Principal (Dashboard)

Após o login, você verá:

### Barra Lateral Esquerda (Menu de Navegação)
- **1. Painel e Gestão** (apenas coordenadores)
- **2. Relatório**
  - Sumário
  - Editor de conteúdo ← **você trabalhará aqui**
  - Modelos Word (.dotx)
- **3. Administração** (apenas coordenadores)

### Área Central
- Lista de relatórios cadastrados (D20-10, D20-11, D20-12...)
- Status de cada relatório (aberto, em revisão, finalizado)

---

## 3. Navegação até Sua Seção

### 3.1. Acessar o Relatório Atual

1. No menu lateral, clique em **"2. Relatório"**
2. Clique em **"Sumário"** (rota: `/relatorios/{rel_id}`)
3. Você verá a estrutura completa do relatório com todas as seções:
   - 1. Apresentação
   - 2. Histórico do Contrato
   - 3. Relação de Produtos Entregues
   - 4. Visão Geral das Atividades Realizadas
     - 4.1. Coordenação
     - 4.2. Atividades Sistema de Informação
     - 4.3. Comunicação Social
     - 4.4. Atividades de Apoio Técnico
       - 4.4.1. Acompanhamento técnico em reuniões...
       - 4.4.2. Apoio Administrativo...
       - (etc.)

### 3.2. Identificar Sua Seção

- Seções atribuídas a você aparecem com seu nome no campo **"Responsável"**
- O status da seção indica:
  - **Pendente:** ainda não iniciada
  - **Em andamento:** você já começou a preencher
  - **Enviado:** você confirmou os blocos (conteúdo travado)
  - **Aprovada:** coordenador validou seu conteúdo

### 3.3. Abrir o Editor

1. Clique no botão **"Editar"** ao lado da sua seção
2. Você será direcionado para a página **"Gerenciador e editor de seção e upload"**
   - Rota: `/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo`

---

## 4. Página de Edição de Conteúdo

A página está dividida em 4 áreas principais:

### **Seção 1: Coordenação da seção e destino do upload**

Aqui você confirma:
- **Seção alvo:** a seção que está editando (pode trocar se tiver mais de uma)
- **Responsável:** seu nome (obrigatório quando há conteúdo)
- **Status:** 
  - Mude de "Pendente" para "Em andamento" quando começar
  - Mude para "Aprovada" quando terminar (antes de confirmar blocos)

**Importante:** Clique em **"Confirmar"** após qualquer alteração.

---

### **Seção 2: Importar conteúdo**

Você pode importar conteúdo de duas formas:

#### Opção A: Arquivo de Texto (.txt)
1. Prepare um arquivo `.txt` com seu conteúdo estruturado:
   ```
   # Título da Subseção
   
   Parágrafo de texto corrido...
   
   ## Subtítulo
   
   Mais texto...
   
   - Item de lista 1
   - Item de lista 2
   ```

2. Clique em **"Escolher arquivo"** e selecione seu `.txt`
3. Clique em **"Analisar arquivo"**
4. O sistema detectará automaticamente:
   - Títulos (linhas iniciadas com `#`)
   - Subtítulos (linhas iniciadas com `##`)
   - Parágrafos (texto corrido)
   - Listas (linhas iniciadas com `-` ou `•`)

5. Revise os blocos detectados
6. Marque/desmarque os blocos que deseja importar
7. Clique em **"Importar selecionados"**

#### Opção B: Arquivo Word (.docx)
1. Prepare um arquivo `.docx` seguindo o modelo fornecido
2. Importe da mesma forma que o `.txt`
3. O sistema extrairá:
   - Títulos e subtítulos (baseados nos estilos Heading)
   - Parágrafos
   - Listas
   - Tabelas
   - Figuras (imagens embutidas)

---

### **Seção 2.1: Blocos extraídos (subsecções incluídas)**

Após importar ou adicionar conteúdo manualmente, você verá uma tabela com todos os blocos:

| Índice | Título | Tipo | Classe | Textos | Adicionado por | Data | Ações |
|--------|--------|------|--------|--------|----------------|------|-------|
| 4.4.1  | Acompanhamento... | Texto | Parágrafo | 150 pal. | Seu Nome | 15/04/26 | ✓ ✎ × |

**Ações disponíveis:**
- **✓ (Confirmar):** trava o bloco (não pode mais editar sem desbloquear)
- **✎ (Editar):** abre o editor para modificar o conteúdo
- **× (Excluir):** remove o bloco

**Ações em lote:**
- Selecione múltiplos blocos (checkbox)
- Use os botões:
  - **Confirmar:** trava todos os selecionados
  - **Desbloquear:** destrava blocos confirmados (apenas se você for o responsável)
  - **Excluir em lote:** remove todos os selecionados

---

### **Seção 3: Editar bloco existente**

Aqui você pode:

#### 3.1. Criar Novo Bloco Manualmente

1. **Selecione a seção alvo** no dropdown (se tiver mais de uma)
2. **Digite o conteúdo** no editor visual (Quill)
3. Use a barra de ferramentas para formatar:
   - **H1:** Título principal (`# `)
   - **H2:** Subtítulo (`## `)
   - **¶:** Parágrafo normal
   - **≣ Lista:** Converte em lista
   - **• Bullet:** Adiciona marcador
   - **\*\*B\*\*:** Negrito
   - **\_I\_:** Itálico

#### 3.2. Inserir Figura

No painel lateral direito:

1. **Figura existente:**
   - Selecione uma figura já enviada no dropdown
   - Ou clique em **"Upload"** para enviar nova imagem (PNG, JPG, SVG, WEBP até 8 MB)

2. **Preencha:**
   - **Legenda:** descrição da figura (ex: "Vista aérea da obra")
   - **Estilo de indexação:**
     - Por seção: FIGURA 4.1, FIGURA 4.2...
     - Sequencial: FIGURA 1, FIGURA 2...
   - **Posição da legenda:** Superior ou Inferior

3. Clique em **"Inserir figura"**

#### 3.3. Inserir Tabela

No painel lateral direito:

1. **Configure:**
   - **Linhas:** número de linhas de dados (sem contar cabeçalho)
   - **Colunas:** número de colunas

2. **Preencha:**
   - **Legenda:** descrição da tabela
   - **Estilo de indexação:** Por seção ou Sequencial
   - **Posição da legenda:** Superior ou Inferior

3. Clique em **"Nova tabela"**
4. Um editor visual abrirá
5. Preencha as células (clique para editar, Tab para próxima)
6. Use os botões para adicionar/remover linhas e colunas
7. Clique em **"Inserir tabela"**

#### 3.4. Salvar e Confirmar

- **Salvar localmente:** salva rascunho no navegador (não envia ao servidor)
- **Confirmar edição:** envia o bloco ao relatório
- **Salvar tudo no servidor:** grava todos os rascunhos pendentes de uma vez

---

### **Seção 4: Pré-visualização do conteúdo**

No painel direito, você vê em tempo real:
- Como seu conteúdo aparecerá no PDF final
- Formatação no padrão visual Concremat/PLI-SP
- Numeração automática de figuras e tabelas
- Cabeçalhos e rodapés

**Controles:**
- **− / +:** Zoom in/out
- **⟳:** Atualizar pré-visualização
- **⛶ Tela inteira:** Abrir em nova aba

**Exportar relatório:**
- Clique em "Exportar relatório"
- Escolha o escopo:
  - Relatório inteiro
  - Seções selecionadas
  - Somente seções importadas
- Clique em **"Exportar DOCX"**
  - Rota de exportação: `/relatorios/{rel_id}/exportar?formato=docx`

---

## 5. Fluxo de Trabalho Completo

### Passo a Passo Recomendado:

1. **Login** → Acesse `https://sra-pli-starter.onrender.com/login` com e-mail e perfil "Autor"

2. **Navegue até sua seção** → Menu "2. Relatório" > "Sumário" (`/relatorios/{rel_id}`) > Clique em "Editar" na sua seção

3. **Confirme coordenação** → Seção 1: verifique responsável e status, clique "Confirmar"
   - Endpoint: `POST /relatorios/{rel_id}/secoes/{sec_id}/responsavel`

4. **Adicione conteúdo:**
   - **Opção A:** Importe arquivo `.txt` ou `.docx` (Seção 2)
     - Endpoint: `POST /importar/analisar` (análise) e `POST /importar/confirmar` (importação)
   - **Opção B:** Digite manualmente no editor (Seção 3)
     - Endpoint: `POST /relatorios/{rel_id}/secoes/{sec_id}/blocos`

5. **Revise os blocos** → Seção 2.1: verifique a tabela de blocos extraídos

6. **Edite se necessário** → Use ✎ para ajustar conteúdo, adicionar figuras/tabelas

7. **Confirme os blocos** → Selecione todos e clique "Confirmar" (ou confirme um por um com ✓)
   - Endpoint individual: `POST /relatorios/{rel_id}/secoes/{sec_id}/blocos/{bloco_id}/confirmar`
   - Endpoint em lote: `POST /relatorios/{rel_id}/secoes/{sec_id}/blocos/aprovar-lote`

8. **Verifique a pré-visualização** → Seção 4: confira como ficará no PDF final
   - Rota de preview: `/relatorios/{rel_id}/preview?secao_ids={sec_id}`

9. **Mude status para "Aprovada"** → Seção 1: status > "Aprovada" > "Confirmar"
   - Endpoint: `POST /relatorios/{rel_id}/secoes/{sec_id}/status`

10. **Aguarde validação do coordenador** → Você receberá notificação por e-mail

---

## 6. Estados dos Blocos

### Bloco Desbloqueado (Editável)
- Você pode editar, mover e excluir livremente
- Aparece sem marcação especial na tabela

### Bloco Bloqueado (Confirmado)
- Aparece com tag **"Bloqueado"** na tabela
- Não pode ser editado/excluído diretamente
- Para desbloquear:
  - Você (responsável) pode clicar em **↩ (Desbloquear)**
  - Ou solicitar ao coordenador

### Modo Edição (Coordenador)
- Coordenadores podem ativar "Modo edição" para editar blocos confirmados
- Aparece tag **"Modo edição"** nos blocos

---

## 7. Notificações por E-mail

Você receberá e-mails automáticos em momentos-chave:

### E-mail de Abertura
- Quando um novo relatório é criado e você é atribuído a uma seção
- Contém link direto para sua seção

### E-mail de Lembrete
- Enviado alguns dias antes do prazo (configurável pelo coordenador)
- Lembra de enviar seu conteúdo

### E-mail de Última Chamada
- Enviado no dia do prazo
- Alerta que o prazo está encerrando

### E-mail de Validação/Reprovação
- Quando o coordenador valida ou reprova seu conteúdo
- Se reprovado, contém motivo e instruções para correção

---

## 8. Dicas e Boas Práticas

### ✅ Faça

- **Prepare o conteúdo offline** antes de importar (Word ou bloco de notas)
- **Use os modelos fornecidos** (menu "Modelos Word")
- **Confirme blocos gradualmente** conforme termina cada parte
- **Verifique a pré-visualização** antes de confirmar tudo
- **Salve rascunhos localmente** se precisar pausar o trabalho
- **Comunique-se com o coordenador** se tiver dúvidas

### ❌ Evite

- **Não deixe para última hora** — o sistema pode estar sobrecarregado
- **Não confirme blocos incompletos** — depois precisa desbloquear
- **Não use formatação complexa no Word** — pode não ser importada corretamente
- **Não envie figuras muito grandes** (limite: 8 MB por arquivo)
- **Não edite diretamente no banco de dados** — sempre use a interface

---

## 9. Resolução de Problemas

### Problema: Não consigo fazer login
- **Solução:** Verifique se selecionou o perfil correto ("Autor")
- Se esqueceu a senha, use "Esqueci minha senha" (`/recuperar-senha`)
- Contate o coordenador se o problema persistir

### Problema: Não vejo minha seção
- **Solução:** Verifique se o coordenador já atribuiu você como responsável
- Vá em "Sumário" e procure seu nome na coluna "Responsável"

### Problema: Não consigo editar um bloco
- **Solução:** Verifique se o bloco está bloqueado (confirmado)
- Se sim, clique em **↩ (Desbloquear)** ou peça ao coordenador

### Problema: Importação não detectou meus títulos
- **Solução:** Certifique-se de usar `#` para títulos e `##` para subtítulos em `.txt`
- Em `.docx`, use os estilos "Heading 1" e "Heading 2"

### Problema: Figura não aparece na pré-visualização
- **Solução:** Verifique se a figura foi enviada corretamente (até 8 MB)
- Formatos aceitos: PNG, JPG, SVG, WEBP
- Atualize a pré-visualização (botão ⟳)

### Problema: Relatório está "finalizado" e não consigo editar
- **Solução:** Apenas coordenadores podem reverter o status
- Contate o coordenador para reabrir o relatório

---

## 10. Glossário

- **Bloco:** Unidade de conteúdo (parágrafo, título, figura, tabela, lista)
- **Seção:** Capítulo do relatório (ex: 4.4.1)
- **Confirmar:** Travar um bloco (marcar como pronto)
- **Desbloquear:** Destravar um bloco confirmado para edição
- **Modo edição:** Permissão especial do coordenador para editar blocos confirmados
- **Escopo:** Conjunto de seções (ex: 4.4 inclui 4.4.1, 4.4.2, etc.)
- **Subárvore:** Seção principal + todas as subseções abaixo dela

---

## 11. Contato e Suporte

- **Sistema em Produção:** https://sra-pli-starter.onrender.com
- **Coordenador do Projeto:** Entre em contato via sistema ou e-mail corporativo
- **Documentação Técnica:** Repositório GitHub do projeto
- **Mapa da Aplicação:** `/mapa-aplicacao` (apenas coordenadores/admin)
- **Status do Sistema:** `/health` (endpoint de healthcheck)

---

**Última atualização:** Abril/2026  
**Versão do Sistema:** SRA v1.0 (PLI/SP-2050)
