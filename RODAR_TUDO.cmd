@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   ATUALIZAR TODO O PROJETO - PO SAUDE ITAUNA
echo ============================================================
echo.
if defined POS_PYTHON (
  "%POS_PYTHON%" -B "%~dp0rodar_tudo.py" %*
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -B "%~dp0rodar_tudo.py" %*
  ) else (
    python -B "%~dp0rodar_tudo.py" %*
  )
)
set "POS_RESULTADO=%ERRORLEVEL%"
echo.
if not "%POS_RESULTADO%"=="0" (
  echo Nao foi possivel concluir. As imagens anteriores foram preservadas.
  echo Consulte ULTIMA_EXECUCAO.log, se o arquivo tiver sido criado.
  echo Se Python nao foi encontrado, instale Python 3 pelo site python.org.
) else (
  echo Concluido. Veja as mensagens acima e ABRIR_RESULTADOS.html.
)
echo.
pause
exit /b %POS_RESULTADO%
