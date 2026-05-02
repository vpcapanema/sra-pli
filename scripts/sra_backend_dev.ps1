# Levanta o Uvicorn em desenvolvimento e, em background, abre o browser em / e /mapa-aplicacao
# quando /health responder 200. Uso: a partir da raiz do repositorio (tasks VS Code / Cursor).
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
$envPath = Join-Path $repo ".env"
if (Test-Path $envPath) {
    Get-Content $envPath | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
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

& $py -u -m uvicorn app.main:app --host $ListenHost --port $Port --reload --log-level info
