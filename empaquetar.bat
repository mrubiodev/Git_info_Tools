@REM Use script directory as base to make paths reliable
set "SCRIPT_DIR=%~dp0"
setlocal EnableDelayedExpansion

IF EXIST "%SCRIPT_DIR%build\" RMDIR /S /Q "%SCRIPT_DIR%build\"
IF EXIST "%SCRIPT_DIR%dist\" RMDIR /S /Q "%SCRIPT_DIR%dist\"

@REM Ensure virtualenv exists; if not, try to create it using system Python
if not exist "%SCRIPT_DIR%.venv\" (
    echo .venv not found; attempting to create using system Python...
    pushd "%SCRIPT_DIR%"
    python -m venv ".venv"
    if exist ".venv\Scripts\python.exe" (
        echo Virtualenv creado correctamente.
        .venv\Scripts\python.exe -m pip install --upgrade pip
        if exist "requirements.txt" (
            echo Instalando dependencias desde requirements.txt en el virtualenv...
            .venv\Scripts\python.exe -m pip install -r "requirements.txt"
        ) else (
            echo No se encontró requirements.txt; omitiendo instalacion de dependencias en venv.
        )
    ) else (
        echo No se pudo crear el virtualenv; se continuará con Python del sistema.
    )
    popd
)

@REM Set VENV_PY and VENV_PIP to venv executables if available, fallback to system
if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
    set "VENV_PIP=%SCRIPT_DIR%.venv\Scripts\python.exe -m pip"
    echo Using virtualenv python: %VENV_PY%
) else (
    set "VENV_PY=python"
    set "VENV_PIP=python -m pip"
    echo Using system python
)

@REM Try to activate for convenience (not required because we call venv python directly)
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    pushd "%SCRIPT_DIR%.venv\Scripts\"
    call activate.bat
    popd
)

%VENV_PIP% install pyinstaller

REM Ensure runtime dependencies are installed so PyInstaller can detect and include them
if exist "%SCRIPT_DIR%requirements.txt" (
    echo Instalando dependencias desde requirements.txt
    %VENV_PIP% install -r "%SCRIPT_DIR%requirements.txt"
) else (
    echo requirements.txt no encontrado; instalando paquetes mínimos (gitpython, openpyxl)
    %VENV_PIP% install gitpython openpyxl
)

REM Configurable entrypoint
set "ENTRYPOINT=main.py"

REM Extract metadata from res\metadata.json using PowerShell
echo Extrayendo metadata del proyecto...
for /f "delims=" %%A in ('powershell -NoProfile -Command "if (Test-Path -Path '%SCRIPT_DIR%res\\metadata.json') { $j = Get-Content -Raw -Path '%SCRIPT_DIR%res\\metadata.json' | ConvertFrom-Json; Write-Output ($j.name + '|' + $j.owner + '|' + $j.version) }"') do set META=%%A

for /f "tokens=1,2,3 delims=|" %%a in ("%META%") do (
    set PROJECT=%%a
    set AUTHOR=%%b
    set VERSION=%%c
)

REM Fallback values if extraction fails
if "%PROJECT%"=="" set PROJECT=GitBranchInfo
if "%AUTHOR%"=="" set AUTHOR=Mrubiodev
if "%VERSION%"=="" set VERSION=%__version__%

echo Metadata extraida: %PROJECT% v%VERSION% por %AUTHOR%

REM Prepare zip names early
set "ZIP_NAME=%PROJECT%_%VERSION%.zip"
set "ZIP_PATH=%SCRIPT_DIR%release\%ZIP_NAME%"

REM Allow showing console by passing second arg 'console' or 'showconsole'
set CONSOLE=0
if "%~2"=="console" set CONSOLE=1
if /I "%~2"=="showconsole" set CONSOLE=1

if "%CONSOLE%"=="0" (
    set "CONSOLE_FLAG=--noconsole"
) else (
    set "CONSOLE_FLAG="
)

echo Empaquetando EXE como %PROJECT%.exe (version %VERSION%) usando entrada %ENTRYPOINT% (console=%CONSOLE%)

%VENV_PY% -m PyInstaller -n "%PROJECT%" -i "%SCRIPT_DIR%res\app_icon.ico" --collect-data TKinterModernThemes --hidden-import git --hidden-import openpyxl %CONSOLE_FLAG% --onefile "%SCRIPT_DIR%%ENTRYPOINT%"

if exist "%SCRIPT_DIR%dist\" (
    REM Actualizar el archivo de requisitos si la carpeta dist existe
    echo Actualizando el archivo de requisitos...
    %VENV_PIP% freeze > "%SCRIPT_DIR%requirements.txt"
    echo Archivo de requisitos actualizado exitosamente.

    echo Copiando el archivo de requisitos a la carpeta dist...
    copy "%SCRIPT_DIR%requirements.txt" "%SCRIPT_DIR%dist\"
    echo Archivo de requisitos copiado exitosamente.

    if exist "%SCRIPT_DIR%resources_release\" (
        echo Ambas carpetas existen. Copiando archivos...
        xcopy /E /I /Y  "%SCRIPT_DIR%resources_release\" "%SCRIPT_DIR%dist\"
        echo Archivos copiados exitosamente.
    ) else (
        echo La carpeta "%SCRIPT_DIR%dist/" existe, pero la carpeta "resources_release" no.
    )

    REM Create release directory and zip dist into release\<project>_<version>.zip
    if not exist "%SCRIPT_DIR%release" mkdir "%SCRIPT_DIR%release"
    echo Comprimiendo %SCRIPT_DIR%dist\ en %ZIP_PATH%
    if exist "%ZIP_PATH%" (
        del /Q "%ZIP_PATH%"
    )
    powershell -NoProfile -Command "Compress-Archive -Path '%SCRIPT_DIR%dist\*' -DestinationPath '%ZIP_PATH%' -Force"
    if exist "%ZIP_PATH%" (
        echo Archivo comprimido creado: %ZIP_PATH%
    ) else (
        echo Error: no se creo el zip %ZIP_PATH%
    )
) else (
    if exist "%SCRIPT_DIR%resources_release\" (
        echo La carpeta "%SCRIPT_DIR%dist/" no existe, pero la carpeta "resources_release" si.
    ) else (
        echo Ninguna de las dos carpetas existe.
    )
)

endlocal

pause