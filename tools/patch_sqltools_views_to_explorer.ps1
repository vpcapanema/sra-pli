#Requires -Version 5.1
# Coloca Connections/Bookmarks/Query History do SQLTools na mesma coluna do Explorador
# (contentor "explorer" do VS Code / Cursor). Executar se a extensao mtxr.sqltools
# tiver o icone separado (manifesto de fabrica).
# Depois: Ctrl+Shift+P > Developer: Reload Window

$ErrorActionPreference = "Stop"
# Apenas mtxr.sqltools-0.x (nao sqltools-driver-* / formatters)
$extRoot = Join-Path $env:USERPROFILE ".cursor\extensions"
$pkg = Get-ChildItem -Path $extRoot -Filter "package.json" -Recurse -ErrorAction SilentlyContinue |
    Where-Object {
        $d = (Split-Path $_.DirectoryName -Leaf)
        $d -match '^mtxr\.sqltools-[0-9]' -and $d -notmatch 'driver|formatter'
    } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $pkg) {
    Write-Error "Nao encontrei mtxr.sqltools em $extRoot"
    exit 1
}

$path = $pkg.FullName
$raw = [System.IO.File]::ReadAllText($path)
if ($raw -match '"explorer"\s*:\s*\[[\s\S]{0,2000}?sqltoolsViewConnectionExplorer') {
    Write-Host "Ja aplicado: $path"
    exit 0
}

$before = $raw
# So o primeiro bloco "sqltoolsActivityBarContainer" em views
$raw = [regex]::Replace($raw, '"sqltoolsActivityBarContainer"\s*:\s*\[', '"explorer": [', 1)
# Remove o contentor do activity bar; deixa o painel
$raw = [regex]::Replace(
    $raw,
    '"activitybar"\s*:\s*\[\s*\{\s*"id"\s*:\s*"sqltoolsActivityBarContainer"[\s\S]*?"title"\s*:\s*"SQLTools"[\s\S]*?\}\s*\]',
    '"activitybar": []',
    1
)
if ($before -eq $raw) {
    Write-Error "Nao alterei o ficheiro (formato inesperado). Rev: $path"
    exit 1
}
[System.IO.File]::Copy($path, "$path.bak", $true)
[System.IO.File]::WriteAllText($path, $raw, [System.Text.UTF8Encoding]::new($false))
Write-Host "OK: $path`nBackup: $path.bak`nRecarregue: Developer: Reload Window (Ctrl+Shift+P)"
