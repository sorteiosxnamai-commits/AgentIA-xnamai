# Smoke GETs — homologação Mercos (não imprime tokens)
param(
    [string]$Base = "https://agent-ia-xnamai.onrender.com",
    [string]$Token = $env:SYNC_TOKEN
)

$ErrorActionPreference = "Stop"
Write-Host "BASE=$Base"
$qs = if ($Token) { "token=$Token&max_paginas=1" } else { "max_paginas=1" }

$paths = @(
    "/mercos/homologacao",
    "/mercos/categorias",
    "/mercos/produtos",
    "/mercos/clientes",
    "/mercos/condicoes-pagamento",
    "/mercos/segmentos",
    "/mercos/tabelas-preco",
    "/mercos/usuarios"
)

foreach ($p in $paths) {
    $url = if ($p -eq "/mercos/homologacao") {
        "$Base$p" + $(if ($Token) { "?token=$Token" } else { "" })
    } else {
        "$Base$p?$qs"
    }
    try {
        $r = Invoke-RestMethod $url
        $total = $r.total
        Write-Host "OK $p total=$total"
    } catch {
        Write-Host "FAIL $p $_"
    }
    Start-Sleep -Seconds 8
}
