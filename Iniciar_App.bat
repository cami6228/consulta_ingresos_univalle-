@echo off
title Consulta de Ingresos - Universidad del Valle
echo ==============================================================
echo  INICIANDO CONSULTA DE INGRESOS - UNIVERSIDAD DEL VALLE
echo ==============================================================
echo.

cd /d "%~dp0"

:: 1. Verificar si Python esta instalado
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [ERROR] No se encontro Python instalado en este equipo.
        echo.
        echo Para usar la aplicacion, instala Python:
        echo 1. Descargalo desde: https://www.python.org/downloads/
        echo 2. IMPORTANTE: Durante la instalacion, marca la casilla:
        echo    "Add python.exe to PATH"
        echo.
        pause
        exit /b 1
    )
    set PYTHON_CMD=py
) else (
    set PYTHON_CMD=python
)

:: 2. Crear entorno virtual e instalar librerias si es la primera vez
if not exist "venv\Scripts\activate.bat" (
    echo [CONFIGURACION INICIAL] Preparando la aplicacion por primera vez...
    echo Esto puede tardar 1 o 2 minutos mientras se descargan las librerias.
    echo Por favor espera...
    echo.
    %PYTHON_CMD% -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
    echo Instalando componentes necesarios...
    venv\Scripts\python -m pip install --quiet --upgrade pip
    venv\Scripts\pip install --quiet -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Ocurrio un problema al instalar los componentes.
        pause
        exit /b 1
    )
    echo [OK] Configuracion inicial completada con exito.
    echo.
)

:: 3. Iniciar aplicacion
echo Abriendo la aplicacion en tu navegador web...
echo (Para cerrar la aplicacion cuando termines, simplemente cierra esta ventana)
echo.
venv\Scripts\streamlit run app.py

pause
