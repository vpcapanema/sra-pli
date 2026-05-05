# =====================================================================
# Correcao do PATH do sistema Windows
# Uso: clique direito -> "Executar com PowerShell" como Administrador
#      ou abra PowerShell como Admin e rode: .\tmp_fix_path.ps1
# =====================================================================

# Checagem de admin
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERRO: este script precisa rodar como Administrador." -ForegroundColor Red
    Write-Host "Feche esta janela, abra PowerShell com 'Executar como administrador' e rode de novo." -ForegroundColor Yellow
    Read-Host "Pressione Enter para sair"
    exit 1
}

# 1) Backup do PATH atual
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = "$env:USERPROFILE\path-machine-$stamp.txt"
[System.Environment]::GetEnvironmentVariable("Path", "Machine") | Out-File $backupFile -Encoding UTF8
Write-Host "Backup salvo em: $backupFile" -ForegroundColor Green

# 2) Entradas essenciais do Windows que estao faltando
$wanted = @(
    'C:\Windows\system32',
    'C:\Windows',
    'C:\Windows\System32\Wbem',
    'C:\Windows\System32\WindowsPowerShell\v1.0\',
    'C:\Windows\System32\OpenSSH\'
)

$current = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$currentList = $current -split ';' | Where-Object { $_ -ne '' }
$toAdd = $wanted | Where-Object { $_ -notin $currentList }

if ($toAdd.Count -eq 0) {
    Write-Host "Nada a adicionar - PATH ja contem as entradas do Windows." -ForegroundColor Yellow
} else {
    Write-Host "Adicionando as seguintes entradas ao PATH do sistema (no inicio, para prioridade):" -ForegroundColor Cyan
    $toAdd | ForEach-Object { Write-Host "  + $_" }

    $newPath = (($toAdd + $currentList) -join ';')
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Host "`nPATH do sistema atualizado com sucesso." -ForegroundColor Green

    Write-Host "`nPrimeiras entradas do novo PATH:" -ForegroundColor Cyan
    [System.Environment]::GetEnvironmentVariable("Path", "Machine") -split ';' | Select-Object -First 10 | ForEach-Object { Write-Host "  $_" }
}

Write-Host "`nPROXIMOS PASSOS:" -ForegroundColor Magenta
Write-Host "  1. Feche TODAS as janelas de PowerShell, CMD, VS Code, Verdent." -ForegroundColor Yellow
Write-Host "  2. Faca logoff e login no Windows (ou reinicie) para propagar." -ForegroundColor Yellow
Write-Host "  3. Abra um PowerShell novo e rode: where.exe powershell" -ForegroundColor Yellow
Write-Host "     Deve retornar C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ForegroundColor Yellow
Read-Host "`nPressione Enter para sair"
