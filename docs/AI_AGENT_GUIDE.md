# SRA - Sistema de Relatórios de Atividades (PLI/SP-2050)
## Guia para Agentes de IA

## Visão Geral
SRA é um sistema de relatórios mensais para contrato PLI/SP-2050. **Roda em produção real** - sem mocks ou dados fictícios.

## Stack
- **Backend**: FastAPI (Python 3.12+), SQLAlchemy, PostgreSQL
- **Frontend**: Jinja2, CSS customizado, Vanilla JS
- **Email**: SendGrid
- **UI**: SweetAlert2 (confirmações/loading)

## Arquivos OBRIGATÓRIOS (Leia antes de alterar código)
1. **`.cursor/project-instructions.md`** - Stack, modelo de domínio, permissões, fluxos
2. **`docs/AI_AGENT_WELCOME_PROMPT.md`** - Objetivos, arquitetura, credenciais
3. **`.cursor/rules/linting.mdc`** - Regras de linting (mantenha Problemas zerada)
4. **`pyproject.toml`** - Configurações de linting
5. **`app/models.py`** - Modelos SQLAlchemy (Relatorio, Secao, Bloco, User)
6. **`app/routes/relatorios.py`** - Criação de relatórios, clonagem, PDF
7. **`app/static/js/sra_process_ui.js`** - UI JavaScript (SweetAlert2)

## Fluxos Principais

### Criação de Relatório (POST /relatorios)
**Fontes de seções**:
- **Clonar relatório**: Copia seções E blocos
- **PDF disponível**: Extrai APENAS sumário (não blocos)
- **Upload PDF**: Extrai sumário do PDF

### Notificações
**Arquivos**: `app/notificacoes/service.py`, `email_sender.py`
- Ciclo mensal: Abertura → Lembrete → Última chamada
- Config: `SENDGRID_API_KEY` em `.env`, `NOTIFICAR_HABILITADO=true`

### UI JavaScript
**Arquivo**: `app/static/js/sra_process_ui.js`
- Confirmações via SweetAlert2
- Loading para processos longos
- Atributos: `data-sra-confirm`, `data-sra-iniciar-acompanhamento`

## Convenções
- **Python**: 4 espaços, aspas duplas, type hints obrigatórios
- **JavaScript**: Vanilla, `var` (compatibilidade), aspas duplas em HTML
- **Jinja2**: 2 espaços, djLint
- **Linting**: Zero erros Flake8/Pylint/djLint

## Credenciais
- **NUNCA** em código versionado
- Estão em `.env` (não versionado)
- Chaves: `SENDGRID_API_KEY`, `DATABASE_URL`, `SECRET_KEY`

## Setup Local
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

## Importante
- PDF disponível extrai APENAS sumário, não blocos
- Formulários `display:none` podem não ser detectados pelo JS
- Sempre verifique linting após alterações
