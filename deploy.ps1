# Deploy Magic Formula reports to GitHub Pages
# Rode após executar o pipeline: .\deploy.ps1

$ROOT = $PSScriptRoot

# Copiar relatórios para docs/
if (Test-Path "$ROOT\output\relatorio.html") {
    Copy-Item "$ROOT\output\relatorio.html" "$ROOT\docs\index.html" -Force
    Write-Host "[deploy] relatorio.html -> docs/index.html"
}

if (Test-Path "$ROOT\output\relatorio_backtest.html") {
    Copy-Item "$ROOT\output\relatorio_backtest.html" "$ROOT\docs\backtest.html" -Force
    Write-Host "[deploy] relatorio_backtest.html -> docs/backtest.html"
}

# Git commit e push
Set-Location $ROOT
git add docs/index.html docs/backtest.html output/candidates.json output/analyses.json output/backtest.json

$hoje = Get-Date -Format "yyyy-MM-dd"
$status = git diff --staged --name-only
if ($status) {
    git commit -m "Relatorios atualizados $hoje"
    git push
    Write-Host "[deploy] Push realizado. Site: https://isaklucas.github.io/MagicFormula/"
} else {
    Write-Host "[deploy] Sem mudancas para commitar."
}
