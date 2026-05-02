# Levanta o Uvicorn em desenvolvimento e, em background, abre o browser em / e /mapa-aplicacao
# Quando /health responder 200, abre o browser. Uso: a partir da raiz do repositório.
param(
    [string] $ListenHost = "127.0.0.1",
    [int] $Port = 8001,
    [switch] $ClearDatabaseUrl
)

$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repo
if ($ClearDatabaseUrl) {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
}
$env:PYTHONUNBUFFERED = "1"
$base = "http://${ListenHost}:${Port}"
$py = Join-Path $repo ".venv/Scripts/python.exe"
if (-not (Test-Path $py)) {
    throw "Interpretador nao encontrado: $py (crie a venv e pip install -r requirements.txt)."
}

# Liberação da porta alvo. Cuidado: o uvicorn antigo às vezes deixa filhos
# multiprocessing.spawn órfãos cujo pai (PID original que fez bind) já morreu;
# nesse caso o netstat ainda mostra o PID do pai morto, mas quem segura o socket
# é o filho herdado. Por isso a varredura é em três camadas (filhos → pais → CmdLine),
# nessa ordem, para não criar zumbis no meio do caminho.

$procsSnapshot = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
$pidsVivos = @{}
foreach ($pp in $procsSnapshot) { $pidsVivos[[int]$pp.ProcessId] = $pp }

function Stop-PidSafe([int] $TargetPid) {
    if (-not $TargetPid -or $TargetPid -eq $PID) { return }
    try { Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue } catch {}
}

$netconns = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
$listeners = @()
foreach ($n in $netconns) {
    if ($n.State -eq 'Listen') { $listeners += [int]$n.OwningProcess }
}
$listeners = $listeners | Where-Object { $_ } | Select-Object -Unique

# 1) filhos diretos dos listeners: workers spawn que herdaram o socket
foreach ($pp in $procsSnapshot) {
    if ($listeners -contains [int]$pp.ParentProcessId) { Stop-PidSafe ([int]$pp.ProcessId) }
}

# 2) os próprios listeners (pode ser cache stale; ignorado se o PID já não existe)
foreach ($pidListener in $listeners) { Stop-PidSafe $pidListener }

# 3) qualquer processo cujo CommandLine identifique o servidor da app (python -m uvicorn / app.main:app).
#    Não inclua "sra_backend_dev.ps1" no regex: o nome do script aparece na CommandLine dos pwsh
#    ancestrais que estão executando este próprio arquivo, e o Stop-Process derrubaria o terminal
#    antes de chegar ao uvicorn.
foreach ($pp in $procsSnapshot) {
    if (-not $pp.CommandLine) { continue }
    if ([int]$pp.ProcessId -eq $PID) { continue }
    if ($pp.CommandLine -match 'python(?:w)?\.exe.+uvicorn|app\.main:app') {
        Stop-PidSafe ([int]$pp.ProcessId)
    }
}

# 4) workers multiprocessing.spawn cujo parent_pid já não existe (órfãos absolutos).
#    Esses geralmente sobreviveram a uma queda anterior do uvicorn com --reload/--workers
#    e continuam segurando handles de socket. CommandLine traz "parent_pid=NNN".
foreach ($pp in $procsSnapshot) {
    if (-not $pp.CommandLine) { continue }
    if ($pp.CommandLine -notmatch 'multiprocessing\.spawn') { continue }
    if ($pp.CommandLine -notmatch 'parent_pid=(\d+)') { continue }
    $pidPai = [int]$Matches[1]
    if (-not $pidsVivos.ContainsKey($pidPai)) { Stop-PidSafe ([int]$pp.ProcessId) }
}

Start-Sleep -Milliseconds 400

# Verificação final: se ainda houver listener, o problema é externo (processo elevado,
# socket preso pelo kernel) e o uvicorn vai falhar com WinError 10048 logo abaixo,
# o que torna o sintoma visível em vez de o terminal cair em silêncio.
$ainda = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
    Where-Object { $_.State -eq 'Listen' }
if ($ainda) {
    Write-Warning ("Porta $Port ainda ocupada por PID(s): " +
        (($ainda.OwningProcess | Select-Object -Unique) -join ', ') +
        ". Vou continuar e deixar o uvicorn reportar o erro de bind.")
}

# Carrega variáveis do .env importantes para o dev server (ex.: SENDGRID_EVENT_WEBHOOK_TOKEN)
$envPath = Join-Path $repo ".env"
if (Test-Path $envPath) {
    $envLines = Get-Content $envPath
    foreach ($ln in $envLines) {
        $line = $ln.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            continue
        }
        $parts = $line.Split("=", 2)
        $key = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($key -eq "SENDGRID_EVENT_WEBHOOK_TOKEN" -and -not $env:SENDGRID_EVENT_WEBHOOK_TOKEN) {
            $env:SENDGRID_EVENT_WEBHOOK_TOKEN = $value
        }
    }
}

Get-Job -Name sra-open -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue
Start-Job -Name sra-open -ScriptBlock {
    param ($BaseUrl)
    $health = "$BaseUrl/health"
    for ($i = 0; $i -lt 120; $i++) {
        try {
            $r = Invoke-WebRequest $health -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) {
                Start-Process "$BaseUrl/"
                Start-Process "$BaseUrl/mapa-aplicacao"
                break
            }
        } catch {
            # ainda a subir
        }
        Start-Sleep -Milliseconds 500
    }
} -ArgumentList $base | Out-Null

& $py -u -m uvicorn app.main:app --host $ListenHost --port $Port --log-level info
