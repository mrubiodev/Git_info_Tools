@echo off
REM Crear un virtualenv local en .venv, activarlo e instalar requirements.txt si existe
set "carpeta=%cd%\.venv"

IF EXIST "%carpeta%" (
    echo Eliminando entorno virtual existente: %carpeta%
    RMDIR /S /Q "%carpeta%"
)

echo Creando entorno virtual en %carpeta% ...
python -m venv "%carpeta%"

IF NOT EXIST "%carpeta%\Scripts\activate.bat" (
    echo No se pudo crear el entorno virtual. Verifica que Python esté en el PATH.
    exit /b 1
)

echo Activando entorno virtual...
call "%carpeta%\Scripts\activate.bat"

IF EXIST "%cd%\requirements.txt" (
    echo Instalando dependencias desde requirements.txt ...
    python -m pip install --upgrade pip
    python -m pip install -r "%cd%\requirements.txt"
) ELSE (
    echo No se encontró requirements.txt, omitiendo instalacion de dependencias.
)

echo Entorno creado y dependencias instaladas (si habia requirements.txt).
echo Para activar manualmente en PowerShell:
echo    .\%carpeta%\Scripts\Activate.ps1
echo Para activar manualmente en CMD:
echo    %carpeta%\Scripts\activate.bat