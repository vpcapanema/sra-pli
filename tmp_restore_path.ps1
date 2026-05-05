# =====================================================================
# Restauracao do PATH a partir de um backup
# Uso: PowerShell como Administrador
#      .\tmp_restore_path.ps1 -BackupFile "C:\Users\...\path-machine-YYYYMMDD-HHMMSS.txt"
# ======================================'===============================

param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile
)

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERRO: este script precisa rodar como Administrador." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

if (-not (Test-Path $BackupFile)) {
    Write-Host "ERRO: arquivo de backup nao encontrado: $BackupFile" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

$conteudo = (Get-Content $BackupFile -Raw).Trim()
if (-not $conteudo) {
    Write-Host "ERRO: backup vazio." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

[System.Environment]::SetEnvironmentVariable("Path", $conteudo, "Machine")
Write-Host "PATH restaurado a partir de: $BackupFile" -ForegroundColor Green
Read-Host "Pressione Enter para sair"
