# SRA — pipeline de commit + push + acompanhamento de deploy no Render.
#
# Etapas:
#   1. Pre-flight: branch, remote, RENDER_API_KEY presente.
#   2. git status -sb (visualizacao).
#   3. git pull --rebase --autostash (sincronizacao com origin/<branch>).
#   4. git add -A + diff stat (stage de tudo, mostra o que vai entrar).
#   5. Lint filtrado pelos arquivos staged (*.py, *.html via --paths).
#      Se houver issues nesses arquivos, des-stagea (git reset) e aborta.
#      Warnings legados em arquivos NAO commitados ficam fora do escopo
#      (alinhado com .cursor/rules/linting.mdc: "nao adicione novas violacoes").
#      -SkipLint pula essa etapa.
#   6. git commit -m "$Message".
#   7. git push origin HEAD.
#   8. Polling do Render via CLI: aguarda deploy com commit.id == HEAD aparecer
#      e segue ate estado terminal. Mostra status + tempo decorrido a cada iteracao.
#      -SkipDeploy pula esta etapa e o health-check (ideal para tasks do Cursor).
#   9. Health-check final em $RenderUrl/health.
#
# Uso:
#   pwsh -File scripts/sra_commit_deploy.ps1 -Message "feat: ..."
#   pwsh -File scripts/sra_commit_deploy.ps1 -Message "fix: ..." -SkipDeploy
#   pwsh -File scripts/sra_commit_deploy.ps1 -Message "chore: ..." -SkipLint -SkipDeploy
#
# Pre-requisitos:
#   - Render CLI instalada e autenticada (RENDER_API_KEY no env do usuario).
#   - Permissao de push para origin.
#   - .venv com requirements (para o dump_agent_diagnostics.py).

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $Message,

    [string] $ServiceId = $(if ($env:RENDER_SERVICE_ID) { $env:RENDER_SERVICE_ID } else { "srv-d7oiv8dckfvc73ae73u0" }),
    [string] $ServiceName = "sra-pli-starter",
    [string] $RenderUrl = "https://sra-pli-starter.onrender.com",
    [string] $HealthPath = "/health",

    [int] $TimeoutMinutes = 20,
    [int] $PollSeconds = 6,

    [switch] $SkipLint,
    [switch] $NoPull,
    [switch] $NoHealthCheck,
    [switch] $SkipDeploy
)

$ErrorActionPreference = "Stop"

# ---------- helpers ----------------------------------------------------------

function Write-Section([string] $title) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor DarkGray
    Write-Host (" {0}" -f $title) -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor DarkGray
}

function Fail([string] $msg, [int] $code = 1) {
    Write-Host ""
    Write-Host "ABORTADO: $msg" -ForegroundColor Red
    exit $code
}

function Run([string] $label, [scriptblock] $block) {
    Write-Host "→ $label" -ForegroundColor Yellow
    & $block
    if ($LASTEXITCODE -ne 0) {
        Fail "$label falhou (exit $LASTEXITCODE)" $LASTEXITCODE
    }
}

function Get-RenderCli {
    $cmd = Get-Command render -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:USERPROFILE "bin\render.exe"
    if (Test-Path $fallback) { return $fallback }
    Fail "Render CLI nao encontrada (esperado em PATH ou em $fallback)."
}

function Format-Elapsed([datetime] $start) {
    $d = (Get-Date) - $start
    return "{0:00}:{1:00}" -f [int]$d.TotalMinutes, $d.Seconds
}

# Estados terminais conhecidos do Render.
$TerminalStates = @(
    "live",
    "build_failed",
    "update_failed",
    "pre_deploy_failed",
    "canceled",
    "deactivated"
)
$SuccessStates = @("live")

# ---------- 0. setup ---------------------------------------------------------

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo

# Git abre o pager (less) por defeito em diff/status longos; sem TTY as tasks do
# Cursor ficam presas em "(END)" ate alguem carregar em q. Desliga o pager.
$env:GIT_PAGER = ""

if (-not $Message -or $Message.Trim().Length -lt 3) {
    Fail "Mensagem do commit ausente ou muito curta. Passe -Message 'mensagem'."
}

$renderCli = Get-RenderCli
Write-Host "Render CLI: $renderCli"
if (-not $env:RENDER_API_KEY) {
    Fail "RENDER_API_KEY nao esta no ambiente. Configure no User env e reabra o terminal."
}

# ---------- 1. pre-flight git ------------------------------------------------

Write-Section "1. Pre-flight"
Run "git rev-parse" { git rev-parse --is-inside-work-tree | Out-Null }

$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if (-not $branch -or $branch -eq "HEAD") {
    Fail "Detached HEAD. Faca checkout de uma branch antes."
}
Write-Host "Branch atual: $branch"

$remote = (git config --get "branch.$branch.remote").Trim()
if (-not $remote) { $remote = "origin" }
Write-Host "Remote     : $remote"

# ---------- 2. git status ----------------------------------------------------

Write-Section "2. git status -sb"
git status -sb
if ($LASTEXITCODE -ne 0) { Fail "git status falhou" $LASTEXITCODE }

# ---------- 3. pull rebase ---------------------------------------------------

if (-not $NoPull) {
    Write-Section "3. git pull --rebase --autostash"
    Run "git pull --rebase --autostash" {
        git pull --rebase --autostash $remote $branch
    }
} else {
    Write-Host "(pull pulado por -NoPull)"
}

# ---------- 4. add + diff stat ----------------------------------------------

Write-Section "4. git add -A + diff stat"
Run "git add -A" { git add -A }

$stagedAll = @(git diff --cached --name-only --diff-filter=ACMR)
if (-not $stagedAll -or $stagedAll.Count -eq 0) {
    Fail "Nada para commitar (working tree limpa apos add)."
}
git diff --cached --stat

# ---------- 5. lint filtrado pelos arquivos staged ---------------------------
# dump_agent_diagnostics.py com --paths filtra flake8/pylint por .py e djlint
# por .html que existirem. cspell e markdownlint sempre rodam pelos globs
# internos. Se a lista filtrada nao tem .py/.html, passamos um sentinel
# inexistente para o script omitir flake8/pylint/djlint mas ainda rodar
# cspell/mdlint. Filtrar pelo staged alinha com linting.mdc: "nao adicione
# novas violacoes" — warnings legados em arquivos nao tocados ficam fora.

if (-not $SkipLint) {
    Write-Section "5. Lint filtrado (dump_agent_diagnostics.py --paths [staged])"
    $py = Join-Path $repo ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { Fail "Interpretador da venv nao encontrado: $py" }

    $pathsLint = @($stagedAll | Where-Object { $_ -match '\.(py|html|htm)$' })
    if ($pathsLint.Count -eq 0) {
        Write-Host "Nenhum .py/.html staged. flake8/pylint/djlint serao omitidos."
        Write-Host "cspell + markdownlint rodam pelos globs internos."
        $lintArgs = @("scripts/dump_agent_diagnostics.py", "--paths", "__no_py_html_staged__")
    } else {
        Write-Host "Arquivos no escopo do lint:"
        $pathsLint | ForEach-Object { Write-Host "  - $_" }
        Write-Host ""
        $lintArgs = @("scripts/dump_agent_diagnostics.py", "--paths") + $pathsLint
    }

    & $py $lintArgs
    $lintExit = $LASTEXITCODE
    if ($lintExit -ne 0) {
        Write-Host ""
        Write-Host "Lint falhou (exit $lintExit). Des-stageando para preservar working tree..." -ForegroundColor Yellow
        & git reset HEAD -- @stagedAll 2>&1 | Out-Null
        Fail "dump_agent_diagnostics falhou. Veja artifacts/agent-diagnostics.txt e corrija." $lintExit
    }
} else {
    Write-Host "(lint pulado por -SkipLint)"
}

# ---------- 6. commit --------------------------------------------------------

Write-Section "6. git commit"
Run "git commit -m" { git commit -m $Message }

$commitSha = (git rev-parse HEAD).Trim()
$commitShort = $commitSha.Substring(0, 7)
Write-Host "Commit local: $commitShort  ($commitSha)"

# ---------- 7. push ----------------------------------------------------------

Write-Section "7. git push"
Run "git push" { git push $remote "HEAD:$branch" }

if ($SkipDeploy) {
    Write-Host ""
    Write-Host "(-SkipDeploy) Deploy no Render e health-check nao aguardados." -ForegroundColor DarkYellow
    Write-Section "FINALIZADO"
    Write-Host "Commit  : $commitShort em $branch"
    Write-Host "Push    : origin/$branch"
    Write-Host "URL     : $RenderUrl (deploy em curso ou pendente no painel Render)"
    exit 0
}

# ---------- 8. polling do deploy no Render -----------------------------------

Write-Section "8. Acompanhamento do deploy no Render"
Write-Host "Servico : $ServiceName  ($ServiceId)"
Write-Host "Repo    : sincronizado com $remote/$branch"
Write-Host "Commit  : $commitShort"
Write-Host "Timeout : $TimeoutMinutes min  (poll $PollSeconds s)"
Write-Host ""

$started = Get-Date
$deployId = $null
$lastStatus = ""
$detected = $false

while (((Get-Date) - $started).TotalMinutes -lt $TimeoutMinutes) {
    $rawJson = & $renderCli deploys list $ServiceId --output json --confirm 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $rawJson) {
        Write-Host ("[{0}] (Render CLI sem resposta — retry)" -f (Format-Elapsed $started)) -ForegroundColor DarkYellow
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    try {
        $deploys = $rawJson | ConvertFrom-Json
    } catch {
        Write-Host ("[{0}] (JSON invalido — retry)" -f (Format-Elapsed $started)) -ForegroundColor DarkYellow
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    # Procura deploy referente a este commit (preferencia) ou o mais recente em curso.
    $match = $deploys | Where-Object { $_.commit -and $_.commit.id -eq $commitSha } | Select-Object -First 1
    if (-not $match) {
        # Ainda nao apareceu — auto-deploy demora ate ~30s para detectar push.
        Write-Host ("[{0}] aguardando Render detectar commit $commitShort..." -f (Format-Elapsed $started)) -ForegroundColor DarkGray
        Start-Sleep -Seconds $PollSeconds
        continue
    }

    if (-not $detected) {
        $detected = $true
        $deployId = $match.id
        Write-Host ""
        Write-Host "Deploy detectado: $deployId  trigger=$($match.trigger)" -ForegroundColor Green
        Write-Host "Painel: https://dashboard.render.com/web/$ServiceId/deploys/$deployId"
        Write-Host ""
    }

    $status = $match.status
    if ($status -ne $lastStatus) {
        Write-Host ("[{0}] status: {1}" -f (Format-Elapsed $started), $status) -ForegroundColor Cyan
        $lastStatus = $status
    } else {
        Write-Host ("[{0}] status: {1}" -f (Format-Elapsed $started), $status) -ForegroundColor DarkGray
    }

    if ($TerminalStates -contains $status) {
        Write-Host ""
        if ($SuccessStates -contains $status) {
            Write-Host ("Deploy concluido com SUCESSO em {0}." -f (Format-Elapsed $started)) -ForegroundColor Green
        } else {
            Write-Host ("Deploy terminou em estado de FALHA: {0}" -f $status) -ForegroundColor Red
            Write-Host "Veja logs: $renderCli logs --resources $ServiceId --limit 200"
            exit 2
        }
        break
    }

    Start-Sleep -Seconds $PollSeconds
}

if (-not $detected) {
    Fail "Timeout de $TimeoutMinutes min sem detectar deploy para $commitShort. O autoDeploy do Render esta ligado? Verifique webhook GitHub -> Render."
}
if (-not ($SuccessStates -contains $lastStatus)) {
    if (-not ($TerminalStates -contains $lastStatus)) {
        Fail "Timeout de $TimeoutMinutes min com deploy em status nao-terminal: $lastStatus" 3
    }
}

# ---------- 9. health-check --------------------------------------------------

if (-not $NoHealthCheck) {
    Write-Section "9. Health-check"
    $url = "$RenderUrl$HealthPath"
    Write-Host "GET $url"
    try {
        $resp = Invoke-WebRequest -Uri $url -Method GET -TimeoutSec 30 -UseBasicParsing
        Write-Host ("HTTP {0}  ({1} bytes)" -f $resp.StatusCode, $resp.RawContentLength) -ForegroundColor Green
    } catch {
        Write-Host "Health-check falhou: $($_.Exception.Message)" -ForegroundColor Red
        exit 4
    }
} else {
    Write-Host "(health-check pulado por -NoHealthCheck)"
}

Write-Section "FINALIZADO"
Write-Host "Commit  : $commitShort em $branch"
Write-Host "Deploy  : $deployId ($lastStatus)"
Write-Host "URL     : $RenderUrl"
exit 0
