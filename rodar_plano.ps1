# Pode usar POS_PYTHON para indicar um Python especifico, sem caminho fixo de computador.
$pythonPlano = $env:POS_PYTHON
if (-not $pythonPlano) { $pythonPlano = 'python' }
& $pythonPlano -u (Join-Path $PSScriptRoot 'executar.py') @args
exit $LASTEXITCODE
