# Fluxo do Autor — Diagrama Visual

Este documento contém diagramas visuais do fluxo de trabalho do autor no sistema SRA.

## 1. Fluxo Completo (Visão Geral)

```mermaid
flowchart TD
    Start([Autor recebe e-mail]) --> Login[Login no sistema]
    Login --> Dashboard[Acessar Dashboard]
    Dashboard --> Sumario[Visualizar Sumário do Relatório]
    Sumario --> VerificarSecao{Seção atribuída?}
    
    VerificarSecao -->|Não| Aguardar[Aguardar atribuição do coordenador]
    Aguardar --> Sumario
    
    VerificarSecao -->|Sim| AbrirEditor[Abrir Editor da Seção]
    AbrirEditor --> ConfirmarCoord[Confirmar Responsável e Status]
    ConfirmarCoord --> EscolherMetodo{Escolher método de entrada}
    
    EscolherMetodo -->|Importar| ImportarArquivo[Importar TXT/DOCX]
    EscolherMetodo -->|Manual| DigitarManual[Digitar no Editor]
    
    ImportarArquivo --> AnalisarArquivo[Sistema analisa e detecta blocos]
    AnalisarArquivo --> RevisarBlocos[Revisar blocos detectados]
    RevisarBlocos --> SelecionarBlocos[Selecionar blocos para importar]
    SelecionarBlocos --> ImportarConfirmar[Confirmar importação]
    ImportarConfirmar --> VerBlocos[Ver blocos na tabela]
    
    DigitarManual --> UsarEditor[Usar editor Quill]
    UsarEditor --> AdicionarFiguras{Adicionar figuras/tabelas?}
    AdicionarFiguras -->|Sim| InserirMidia[Inserir figuras/tabelas]
    AdicionarFiguras -->|Não| SalvarBloco[Inserir novo bloco]
    InserirMidia --> SalvarBloco
    SalvarBloco --> VerBlocos
    
    VerBlocos --> EditarNecessario{Precisa editar?}
    EditarNecessario -->|Sim| EditarBloco[Editar bloco existente]
    EditarBloco --> VerBlocos
    
    EditarNecessario -->|Não| VerificarPreview[Verificar pré-visualização]
    VerificarPreview --> PreviewOK{Preview OK?}
    PreviewOK -->|Não| EditarBloco
    
    PreviewOK -->|Sim| ConfirmarBlocos[Confirmar blocos selecionados]
    ConfirmarBlocos --> BlocosConfirmados{Todos confirmados?}
    BlocosConfirmados -->|Não| VerBlocos
    
    BlocosConfirmados -->|Sim| MudarStatus[Mudar status para 'Aprovada']
    MudarStatus --> AguardarValidacao[Aguardar validação do coordenador]
    AguardarValidacao --> ReceberNotif[Receber notificação por e-mail]
    ReceberNotif --> Validado{Validado?}
    
    Validado -->|Sim| Concluido([Concluído!])
    Validado -->|Não| VerMotivo[Ver motivo da reprovação]
    VerMotivo --> DesbloquearBlocos[Desbloquear blocos]
    DesbloquearBlocos --> EditarBloco
    
    style Start fill:#e1f5e1
    style Concluido fill:#e1f5e1
    style Login fill:#fff3cd
    style ConfirmarBlocos fill:#f8d7da
    style MudarStatus fill:#f8d7da
```

## 2. Fluxo de Importação de Conteúdo

```mermaid
flowchart TD
    Start([Iniciar Importação]) --> EscolherArquivo[Escolher arquivo TXT/DOCX]
    EscolherArquivo --> ClicarAnalisar[Clicar 'Analisar arquivo']
    ClicarAnalisar --> Upload[Upload do arquivo]
    Upload --> Processar[Sistema processa arquivo]
    
    Processar --> DetectarBlocos[Detectar blocos automaticamente]
    DetectarBlocos --> TipoArquivo{Tipo de arquivo?}
    
    TipoArquivo -->|TXT| ParseTXT[Parse de Markdown]
    TipoArquivo -->|DOCX| ParseDOCX[Parse de estilos Word]
    
    ParseTXT --> ExtrairTitulos[Extrair títulos #]
    ParseTXT --> ExtrairSubtitulos[Extrair subtítulos ##]
    ParseTXT --> ExtrairParagrafos[Extrair parágrafos]
    ParseTXT --> ExtrairListas[Extrair listas -]
    
    ParseDOCX --> ExtrairHeading1[Extrair Heading 1]
    ParseDOCX --> ExtrairHeading2[Extrair Heading 2]
    ParseDOCX --> ExtrairTexto[Extrair texto normal]
    ParseDOCX --> ExtrairTabelas[Extrair tabelas]
    ParseDOCX --> ExtrairImagens[Extrair imagens]
    
    ExtrairTitulos --> MostrarRevisao
    ExtrairSubtitulos --> MostrarRevisao
    ExtrairParagrafos --> MostrarRevisao
    ExtrairListas --> MostrarRevisao
    ExtrairHeading1 --> MostrarRevisao
    ExtrairHeading2 --> MostrarRevisao
    ExtrairTexto --> MostrarRevisao
    ExtrairTabelas --> MostrarRevisao
    ExtrairImagens --> MostrarRevisao
    
    MostrarRevisao[Mostrar tela de revisão]
    MostrarRevisao --> RevisarBlocos[Autor revisa blocos detectados]
    RevisarBlocos --> MarcarDesmarcar[Marcar/desmarcar blocos]
    MarcarDesmarcar --> AjustarIndices{Ajustar índices?}
    
    AjustarIndices -->|Sim| SincronizarIndices[Sincronizar índices]
    AjustarIndices -->|Não| ConfirmarImport
    SincronizarIndices --> ConfirmarImport[Clicar 'Importar selecionados']
    
    ConfirmarImport --> CriarBlocos[Sistema cria blocos no banco]
    CriarBlocos --> AtualizarTabela[Atualizar tabela de blocos]
    AtualizarTabela --> End([Importação concluída])
    
    style Start fill:#e1f5e1
    style End fill:#e1f5e1
    style ConfirmarImport fill:#f8d7da
```

## 3. Fluxo de Edição Manual

```mermaid
flowchart TD
    Start([Iniciar Edição Manual]) --> AbrirEditor[Abrir editor Quill]
    AbrirEditor --> EscolherTipo{Tipo de conteúdo?}
    
    EscolherTipo -->|Texto| DigitarTexto[Digitar texto]
    EscolherTipo -->|Figura| InserirFigura[Inserir figura]
    EscolherTipo -->|Tabela| InserirTabela[Inserir tabela]
    
    DigitarTexto --> UsarFerramentas[Usar barra de ferramentas]
    UsarFerramentas --> AplicarFormato{Aplicar formato?}
    
    AplicarFormato -->|Título| ClicarH1[Clicar H1]
    AplicarFormato -->|Subtítulo| ClicarH2[Clicar H2]
    AplicarFormato -->|Parágrafo| ClicarP[Clicar ¶]
    AplicarFormato -->|Lista| ClicarLista[Clicar ≣ Lista]
    AplicarFormato -->|Negrito| ClicarBold[Clicar **B**]
    AplicarFormato -->|Itálico| ClicarItalic[Clicar _I_]
    
    ClicarH1 --> TextoFormatado
    ClicarH2 --> TextoFormatado
    ClicarP --> TextoFormatado
    ClicarLista --> TextoFormatado
    ClicarBold --> TextoFormatado
    ClicarItalic --> TextoFormatado
    
    TextoFormatado[Texto formatado] --> VerificarConteudo{Conteúdo OK?}
    VerificarConteudo -->|Não| DigitarTexto
    VerificarConteudo -->|Sim| SalvarBloco
    
    InserirFigura --> FiguraExiste{Figura já existe?}
    FiguraExiste -->|Sim| SelecionarFigura[Selecionar do dropdown]
    FiguraExiste -->|Não| UploadFigura[Upload nova figura]
    
    SelecionarFigura --> PreencherLegenda[Preencher legenda]
    UploadFigura --> PreencherLegenda
    PreencherLegenda --> EscolherEstilo[Escolher estilo de indexação]
    EscolherEstilo --> EscolherPosicao[Escolher posição da legenda]
    EscolherPosicao --> ClicarInserirFig[Clicar 'Inserir figura']
    ClicarInserirFig --> SalvarBloco
    
    InserirTabela --> ConfigurarTabela[Configurar linhas e colunas]
    ConfigurarTabela --> PreencherLegendaTab[Preencher legenda]
    PreencherLegendaTab --> EscolherEstiloTab[Escolher estilo de indexação]
    EscolherEstiloTab --> EscolherPosicaoTab[Escolher posição]
    EscolherPosicaoTab --> ClicarNovaTabela[Clicar 'Nova tabela']
    ClicarNovaTabela --> AbrirEditorVisual[Abrir editor visual]
    AbrirEditorVisual --> PreencherCelulas[Preencher células]
    PreencherCelulas --> AjustarTabela{Ajustar estrutura?}
    
    AjustarTabela -->|Adicionar linha| AddLinha[+ Linha]
    AjustarTabela -->|Remover linha| DelLinha[− Linha]
    AjustarTabela -->|Adicionar coluna| AddCol[+ Coluna]
    AjustarTabela -->|Remover coluna| DelCol[− Coluna]
    AjustarTabela -->|OK| ClicarInserirTab[Clicar 'Inserir tabela']
    
    AddLinha --> PreencherCelulas
    DelLinha --> PreencherCelulas
    AddCol --> PreencherCelulas
    DelCol --> PreencherCelulas
    
    ClicarInserirTab --> SalvarBloco
    
    SalvarBloco[Clicar 'Inserir novo bloco'] --> BlocoSalvo[Bloco salvo no banco]
    BlocoSalvo --> AtualizarTabela[Atualizar tabela de blocos]
    AtualizarTabela --> End([Edição concluída])
    
    style Start fill:#e1f5e1
    style End fill:#e1f5e1
    style SalvarBloco fill:#f8d7da
```

## 4. Fluxo de Confirmação de Blocos

```mermaid
flowchart TD
    Start([Blocos criados]) --> VerTabela[Ver tabela de blocos]
    VerTabela --> EscolherMetodo{Método de confirmação?}
    
    EscolherMetodo -->|Individual| SelecionarUm[Selecionar um bloco]
    EscolherMetodo -->|Lote| SelecionarVarios[Selecionar múltiplos blocos]
    
    SelecionarUm --> ClicarCheck[Clicar ✓ (Confirmar)]
    ClicarCheck --> BlocoConfirmado[Bloco bloqueado]
    BlocoConfirmado --> MaisParaConfirmar{Mais blocos?}
    MaisParaConfirmar -->|Sim| SelecionarUm
    MaisParaConfirmar -->|Não| TodosConfirmados
    
    SelecionarVarios --> MarcarCheckboxes[Marcar checkboxes]
    MarcarCheckboxes --> ClicarConfirmarLote[Clicar 'Confirmar' no topo]
    ClicarConfirmarLote --> BlocosConfirmados[Blocos bloqueados em lote]
    BlocosConfirmados --> TodosConfirmados
    
    TodosConfirmados[Todos os blocos confirmados] --> VerificarStatus[Verificar status da seção]
    VerificarStatus --> StatusAtual{Status atual?}
    
    StatusAtual -->|Pendente| MudarParaAndamento[Mudar para 'Em andamento']
    StatusAtual -->|Em andamento| MudarParaAprovada[Mudar para 'Aprovada']
    StatusAtual -->|Aprovada| StatusOK
    
    MudarParaAndamento --> ClicarConfirmarStatus1[Clicar 'Confirmar']
    MudarParaAprovada --> ClicarConfirmarStatus2[Clicar 'Confirmar']
    ClicarConfirmarStatus1 --> StatusOK
    ClicarConfirmarStatus2 --> StatusOK
    
    StatusOK[Status atualizado] --> NotificarSistema[Sistema notifica coordenador]
    NotificarSistema --> AguardarValidacao[Aguardar validação]
    AguardarValidacao --> ReceberEmail[Receber e-mail de validação]
    ReceberEmail --> ResultadoValidacao{Resultado?}
    
    ResultadoValidacao -->|Aprovado| Concluido([Seção concluída!])
    ResultadoValidacao -->|Reprovado| VerMotivo[Ver motivo da reprovação]
    VerMotivo --> DesbloquearBlocos[Desbloquear blocos]
    DesbloquearBlocos --> ClicarDesbloquear[Clicar ↩ (Desbloquear)]
    ClicarDesbloquear --> BlocoDesbloqueado[Bloco editável novamente]
    BlocoDesbloqueado --> EditarBloco[Editar bloco]
    EditarBloco --> ClicarCheck
    
    style Start fill:#e1f5e1
    style Concluido fill:#e1f5e1
    style ClicarConfirmarLote fill:#f8d7da
    style MudarParaAprovada fill:#f8d7da
```

## 5. Estados e Transições dos Blocos

```mermaid
stateDiagram-v2
    [*] --> Criado: Autor cria bloco
    Criado --> Editavel: Bloco salvo
    Editavel --> Editavel: Autor edita
    Editavel --> Bloqueado: Autor confirma (✓)
    Bloqueado --> Editavel: Responsável desbloqueia (↩)
    Bloqueado --> Validado: Coordenador valida
    Validado --> Editavel: Coordenador reprova
    Validado --> [*]: Relatório finalizado
    
    note right of Editavel
        Ações disponíveis:
        - Editar (✎)
        - Excluir (×)
        - Confirmar (✓)
    end note
    
    note right of Bloqueado
        Ações disponíveis:
        - Desbloquear (↩)
        Apenas responsável ou coordenador
    end note
    
    note right of Validado
        Bloco aprovado pelo coordenador
        Não pode ser editado
    end note
```

## 6. Ciclo de Notificações

```mermaid
sequenceDiagram
    participant Sistema
    participant Autor
    participant Coordenador
    
    Sistema->>Autor: E-mail de Abertura (dia 1)
    Note over Autor: Relatório criado<br/>Seção atribuída
    
    Autor->>Sistema: Login e acesso à seção
    Autor->>Sistema: Adiciona conteúdo
    
    Sistema->>Autor: E-mail de Lembrete (dia 5)
    Note over Autor: Lembrete para enviar
    
    Sistema->>Autor: E-mail de Lembrete (dia 8)
    Note over Autor: Segundo lembrete
    
    Sistema->>Autor: E-mail de Última Chamada (dia 10)
    Note over Autor: Prazo encerrando
    
    Autor->>Sistema: Confirma blocos
    Autor->>Sistema: Muda status para 'Aprovada'
    
    Sistema->>Coordenador: Notificação de entrega
    Note over Coordenador: Autor enviou conteúdo
    
    Coordenador->>Sistema: Valida conteúdo
    
    alt Aprovado
        Sistema->>Autor: E-mail de Validação
        Note over Autor: Conteúdo aprovado!
    else Reprovado
        Sistema->>Autor: E-mail de Reprovação
        Note over Autor: Motivo: [texto]<br/>Corrigir e reenviar
        Autor->>Sistema: Desbloqueia e edita
        Autor->>Sistema: Confirma novamente
    end
```

## 7. Arquitetura de Rotas (Referência Técnica)

```mermaid
graph LR
    A[Cliente/Navegador] --> B[FastAPI App]
    
    B --> C[/login]
    B --> D[/dashboard]
    B --> E[/relatorios/:id]
    B --> F[/relatorios/:id/secoes/:id/upload-conteudo]
    
    F --> G[GET: Carregar editor]
    F --> H[POST: Criar bloco]
    F --> I[POST: Confirmar bloco]
    F --> J[POST: Editar bloco]
    F --> K[POST: Excluir bloco]
    
    H --> L[(PostgreSQL)]
    I --> L
    J --> L
    K --> L
    
    F --> M[/preview]
    M --> N[Renderizar HTML A4]
    
    F --> O[/exportar]
    O --> P[Gerar DOCX]
    
    style A fill:#e1f5e1
    style L fill:#d1ecf1
    style N fill:#fff3cd
    style P fill:#fff3cd
```

---

**Versão:** SRA v1.0 (PLI/SP-2050)  
**Última atualização:** Abril/2026

## Como Visualizar os Diagramas

Estes diagramas estão em formato **Mermaid** e podem ser visualizados:

1. **No GitHub:** Automaticamente renderizados ao visualizar este arquivo `.md`
2. **No VS Code:** Instale a extensão "Markdown Preview Mermaid Support"
3. **Online:** Cole o código em https://mermaid.live/
4. **No Cursor:** Suporte nativo para preview de Mermaid em Markdown
