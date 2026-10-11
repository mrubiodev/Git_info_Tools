@REM Empaqueta la GUI ligera (solo automatizaciones). Mismos argumentos que empaquetar.bat.
@echo off
setlocal
set "ENTRYPOINT=main_lite.py"
set "PROJECT_SUFFIX=_Lite"
call "%~dp0empaquetar.bat" %*
endlocal
