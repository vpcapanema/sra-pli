# Guia Rápido do Autor — SRA (Relatórios D20)

## 🔐 Acesso

**URL:** https://sra-pli-starter.onrender.com/login

| Campo | Valor |
|-------|-------|
| E-mail | Seu e-mail corporativo |
| Perfil | **Autor** |
| Senha | Fornecida pelo coordenador |

---

## 🗺️ Navegação Rápida

| Destino | Caminho |
|---------|---------|
| Dashboard | Menu lateral > **2. Relatório** > Sumário |
| Sua seção | Dashboard > Botão **Editar** na sua seção |
| Modelos Word | Menu lateral > **2. Relatório** > Modelos Word (.dotx) |

---

## 📝 Fluxo de Trabalho (5 Passos)

```
1. LOGIN → 2. ABRIR SEÇÃO → 3. ADICIONAR CONTEÚDO → 4. CONFIRMAR BLOCOS → 5. APROVAR
```

### Detalhamento:

1. **Login** → `https://sra-pli-starter.onrender.com/login`
2. **Abrir seção** → Menu > Sumário > Editar
3. **Adicionar conteúdo** → Importar arquivo OU digitar manualmente
4. **Confirmar blocos** → Selecionar + botão "Confirmar"
5. **Aprovar** → Status > "Aprovada" > Confirmar

---

## 📤 Importar Conteúdo

### Arquivo TXT

```
# Título Principal

Parágrafo de texto corrido...

## Subtítulo

Mais texto...

- Item de lista 1
- Item de lista 2
```

### Arquivo DOCX

- Use estilos **Heading 1** para títulos
- Use estilos **Heading 2** para subtítulos
- Parágrafos normais para texto corrido
- Listas com marcadores (bullets)
- Tabelas e figuras são importadas automaticamente

### Limites

- **Tamanho máximo:** 20 MB por arquivo
- **Formatos aceitos:** `.txt`, `.docx`
- **Figuras:** PNG, JPG, SVG, WEBP (até 8 MB cada)

---

## ✏️ Editor Manual

### Barra de Ferramentas

| Botão | Função | Markdown |
|-------|--------|----------|
| **H1** | Título principal | `# Título` |
| **H2** | Subtítulo | `## Subtítulo` |
| **¶** | Parágrafo | Texto normal |
| **≣ Lista** | Converter em lista | `- Item` |
| **• Bullet** | Adicionar marcador | `- ` |
| **\*\*B\*\*** | Negrito | `**texto**` |
| **\_I\_** | Itálico | `_texto_` |

---

## 🖼️ Inserir Figura

1. **Painel lateral direito** > Seção "🖼 Figura"
2. Selecione figura existente OU clique **"Upload"**
3. Preencha **Legenda** (ex: "Vista aérea da obra")
4. Escolha **Estilo de indexação:**
   - Por seção: FIGURA 4.1, 4.2...
   - Sequencial: FIGURA 1, 2, 3...
5. Escolha **Posição da legenda:** Superior ou Inferior
6. Clique **"Inserir figura"**

---

## 📊 Inserir Tabela

1. **Painel lateral direito** > Seção "▦ Tabela"
2. Configure **Linhas** e **Colunas**
3. Preencha **Legenda**
4. Escolha **Estilo de indexação** e **Posição**
5. Clique **"Nova tabela"**
6. Preencha células no editor visual (Tab para próxima)
7. Clique **"Inserir tabela"**

---

## 🔒 Estados dos Blocos

| Estado | Descrição | Ações Disponíveis |
|--------|-----------|-------------------|
| **Desbloqueado** | Editável livremente | ✓ Confirmar, ✎ Editar, × Excluir |
| **Bloqueado** | Confirmado (travado) | ↩ Desbloquear (apenas responsável) |
| **Modo Edição** | Coordenador editando | Todas (apenas coordenador) |

---

## 📋 Ações em Lote

1. Selecione múltiplos blocos (checkbox)
2. Use botões no topo da tabela:
   - **Confirmar** → Trava todos selecionados
   - **Desbloquear** → Destrava (apenas responsável)
   - **Excluir em lote** → Remove todos selecionados

---

## 📧 Notificações por E-mail

| Tipo | Quando | Ação Esperada |
|------|--------|---------------|
| **Abertura** | Novo relatório criado | Iniciar preenchimento |
| **Lembrete** | Dias 5 e 8 do mês | Continuar/finalizar |
| **Última Chamada** | Dia 10 do mês | Enviar urgente |
| **Validação** | Coordenador aprovou | Nenhuma (concluído) |
| **Reprovação** | Coordenador reprovou | Corrigir e reenviar |

---

## 🎯 Status da Seção

| Status | Significado | Quando Usar |
|--------|-------------|-------------|
| **Pendente** | Não iniciada | Ao receber atribuição |
| **Em andamento** | Trabalhando | Ao começar a preencher |
| **Enviado** | Blocos confirmados | Após confirmar todos os blocos |
| **Aprovada** | Pronta para validação | Antes de confirmar blocos |

**Fluxo recomendado:** Pendente → Em andamento → Aprovada → Confirmar blocos → Enviado

---

## ⚠️ Problemas Comuns

### Não consigo fazer login
- ✅ Verifique se selecionou perfil **"Autor"**
- ✅ Use "Esqueci minha senha" se necessário

### Não vejo minha seção
- ✅ Verifique se coordenador atribuiu você como responsável
- ✅ Procure seu nome na coluna "Responsável" no Sumário

### Não consigo editar bloco
- ✅ Verifique se bloco está bloqueado (confirmado)
- ✅ Clique em **↩ Desbloquear** ou peça ao coordenador

### Importação não detectou títulos
- ✅ Use `#` para títulos e `##` para subtítulos em TXT
- ✅ Use estilos "Heading 1" e "Heading 2" em DOCX

### Figura não aparece
- ✅ Verifique tamanho (máx 8 MB)
- ✅ Formatos aceitos: PNG, JPG, SVG, WEBP
- ✅ Clique no botão ⟳ para atualizar preview

### Relatório "finalizado"
- ✅ Apenas coordenador pode reverter status
- ✅ Contate o coordenador

---

## 🔑 Atalhos e Dicas

### ✅ Faça

- ✅ Prepare conteúdo offline antes de importar
- ✅ Use os modelos Word fornecidos
- ✅ Confirme blocos gradualmente
- ✅ Verifique preview antes de confirmar tudo
- ✅ Salve rascunhos localmente se pausar

### ❌ Evite

- ❌ Deixar para última hora
- ❌ Confirmar blocos incompletos
- ❌ Usar formatação complexa no Word
- ❌ Enviar figuras muito grandes (>8 MB)
- ❌ Editar diretamente no banco de dados

---

## 🔗 Links Úteis

| Recurso | URL |
|---------|-----|
| **Login** | https://sra-pli-starter.onrender.com/login |
| **Dashboard** | https://sra-pli-starter.onrender.com/dashboard |
| **Recuperar Senha** | https://sra-pli-starter.onrender.com/recuperar-senha |
| **Healthcheck** | https://sra-pli-starter.onrender.com/health |

---

## 📞 Suporte

- **Sistema:** https://sra-pli-starter.onrender.com
- **Coordenador:** Contato via sistema ou e-mail corporativo
- **Tutorial Completo:** `docs/TUTORIAL_AUTOR.md`

---

## 📊 Endpoints da API (Referência Técnica)

| Ação | Método | Endpoint |
|------|--------|----------|
| Login | POST | `/login` |
| Sumário | GET | `/relatorios/{rel_id}` |
| Editor | GET | `/relatorios/{rel_id}/secoes/{sec_id}/upload-conteudo` |
| Criar bloco | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos` |
| Confirmar bloco | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos/{bloco_id}/confirmar` |
| Confirmar lote | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos/aprovar-lote` |
| Desbloquear | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos/{bloco_id}/desbloquear` |
| Excluir bloco | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos/{bloco_id}/excluir` |
| Excluir lote | POST | `/relatorios/{rel_id}/secoes/{sec_id}/blocos/excluir-lote` |
| Status seção | POST | `/relatorios/{rel_id}/secoes/{sec_id}/status` |
| Responsável | POST | `/relatorios/{rel_id}/secoes/{sec_id}/responsavel` |
| Preview | GET | `/relatorios/{rel_id}/preview?secao_ids={sec_id}` |
| Exportar DOCX | GET | `/relatorios/{rel_id}/exportar?formato=docx` |
| Importar análise | POST | `/importar/analisar` |
| Importar confirmar | POST | `/importar/confirmar` |

---

**Versão:** SRA v1.0 (PLI/SP-2050)  
**Última atualização:** Abril/2026
