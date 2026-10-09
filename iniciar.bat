@echo off
REM ============================================================
REM  iniciar.bat - Sobe o Reembolso-Tecnored no PC (ambiente local)
REM ============================================================
REM  O que faz:
REM    1. Confere se o Docker Desktop esta rodando.
REM    2. Confere se existem o .env e o docker-compose.override.yml.
REM    3. Recompila e sobe os containers (banco, API e site).
REM       A API roda as migracoes do banco sozinha ao subir.
REM    4. Espera a API ficar saudavel e abre o site no navegador.
REM
REM  Nao roda git: atualize o codigo antes (git pull), se quiser.
REM  Os dados ficam no volume do Docker e NAO sao apagados.
REM
REM  Uso: duplo-clique no arquivo, ou  iniciar.bat  no terminal.
REM ============================================================
setlocal

REM Roda sempre a partir da pasta deste script (raiz do repositorio).
cd /d "%~dp0"

if not defined APP_ENV set "APP_ENV=local"

where docker >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Comando 'docker' nao encontrado.
    echo        Instale o Docker Desktop.
    goto :fim
)

docker info >nul 2>nul
if errorlevel 1 (
    echo [ERRO] O Docker Desktop nao esta rodando.
    echo        Abra o Docker Desktop, espere ficar verde e rode de novo.
    goto :fim
)

if not exist ".env" (
    echo [ERRO] Arquivo .env nao encontrado.
    echo        Copie o .env.example para .env e preencha.
    goto :fim
)

if not exist "docker-compose.override.yml" (
    echo [ERRO] Arquivo docker-compose.override.yml nao encontrado.
    echo        Copie o docker-compose.override.yml.example para docker-compose.override.yml.
    goto :fim
)

echo [iniciar] Recompilando e subindo os containers...
docker compose up -d --build
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao subir os containers. Veja a saida acima.
    goto :fim
)

echo.
echo [iniciar] Aguardando a API ficar saudavel (pode levar ate 1 minuto)...
set /a TENTATIVAS=0
:espera_api
docker inspect --format="{{.State.Health.Status}}" reembolso-backend-%APP_ENV% 2>nul | findstr /i "healthy" | findstr /iv "unhealthy" >nul
if errorlevel 1 (
    set /a TENTATIVAS+=1
    if %TENTATIVAS% geq 40 (
        echo.
        echo [ERRO] A API nao ficou saudavel. Veja o motivo com:
        echo        docker compose logs backend
        goto :fim
    )
    timeout /t 3 /nobreak >nul
    goto :espera_api
)

echo.
docker compose ps

echo.
echo [iniciar] Pronto.
echo           Site: http://localhost:8080
echo           API:  http://localhost:8081
echo           Para parar: docker compose down
start "" "http://localhost:8080"

:fim
echo.
pause
endlocal
