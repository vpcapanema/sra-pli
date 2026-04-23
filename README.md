# SRA — Sistema de Relatórios de Atividades (PLI/SP-2050)

Plataforma web para **produção semi-automática dos Relatórios Mensais D20** do consórcio
Concremat–Transplan no contrato PLI/SP-2050 (SEMIL/DER-SP). Cada autor submete apenas o
conteúdo da sua seção (texto, figuras, tabelas); o sistema compila, formata no padrão
visual Concremat e gera o PDF final pronto para assinatura eletrônica.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2 + Postgres
- **Frontend**: HTML + Jinja2 (sem React, conforme preferência do projeto)
- **PDF**: WeasyPrint (HTML/CSS → PDF/A-ready com `@page`, sumário, cabeçalho e rodapé)
- **Auth**: sessão assinada (`itsdangerous`) + bcrypt
- **Deploy**: Docker + Render (web service + Postgres gerenciado)

## Estrutura

```text
app/
  main.py            # FastAPI + middlewares + rotas
  config.py          # Settings via env
  db.py              # Engine SQLAlchemy
  models.py          # User, Relatorio, Secao, Bloco, Figura
  auth.py            # bcrypt + sessão
  bootstrap.py       # init_db + seed admin + seções padrão
  pdf_render.py      # WeasyPrint + template Concremat
  routes/            # auth, pages, relatorios, blocos, figuras, pdf
  templates/         # UI HTML + pdf/relatorio.html
  static/css/app.css # Tema Concremat/PLI (paleta navy/green)
Dockerfile
render.yaml
requirements.txt
```

## Rodar local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# editar DATABASE_URL e ADMIN_PASSWORD
uvicorn app.main:app --reload
```

Para Postgres local (Docker):

```powershell
docker run -d --name sra-pg -e POSTGRES_PASSWORD=sra -e POSTGRES_DB=sra -p 5432:5432 postgres:16
```

Definir `DATABASE_URL=postgresql+psycopg2://postgres:sra@localhost:5432/sra`.

Acessar `http://localhost:8000` e logar com o admin definido em `.env`.

## Deploy no Render

O `render.yaml` na raiz declara os dois serviços (Postgres + Web). Após criar o **Blueprint**
no Render apontando para este repositório, definir manualmente o segredo `ADMIN_PASSWORD`.

## Funcionalidades v1

- Cadastro de relatórios (`D20-N`) com período, mês, medição, versão (R00, R01…)
- Sumário fixo (1, 2, 3, 4.1…4.4, 5…13) criado automaticamente
- Atribuição de responsável por seção (admin/coordenador)
- Submissão de blocos de conteúdo por seção: **texto / lista / figura / tabela**
- Upload de figuras (PNG/JPG/SVG/WEBP, até 8 MB), armazenadas no banco
- Geração do PDF final no padrão visual Concremat/PLI-SP (capa colorida,
  ficha técnica, sumário, cabeçalho/rodapé, página de assinaturas)
- Versionamento incremental (R00 → R01 → R02…)
- Controle de status: aberto / em revisão / finalizado

## Roadmap

- v2: módulo de reuniões + atas, apêndices automáticos (merge de PDFs externos)
- v3: D21 (planilha de horas + declarações), cronograma físico-financeiro com gráficos
- v4: integração D4Sign API, SharePoint sync, diff entre versões
- v5: dashboards FAD-STATS / SIGMA-PLI embutidos
