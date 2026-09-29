# Git Branch Info & Recovery

![Estado](https://img.shields.io/badge/estado-En%20desarrollo-yellow)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Tkinter](https://img.shields.io/badge/Interfaz-Tkinter-444444)
![GitPython](https://img.shields.io/badge/Git-GitPython-F05032?logo=git&logoColor=white)
![SQLite](https://img.shields.io/badge/Base%20de%20datos-SQLite-003B57?logo=sqlite&logoColor=white)
![Excel](https://img.shields.io/badge/Exportación-XLSX-217346?logo=microsoftexcel&logoColor=white)

Aplicación de escritorio para consultar referencias de ramas remotas de un repositorio Git, buscar candidatos a ramas perdidas en el reflog local y guardar los resultados en una base SQLite. Versión del código: **V26.02.014**.

## Funciones

- Actualiza los remotos configurados y consulta las ramas de seguimiento del remoto predeterminado.
- Muestra el último commit de cada rama: hash, fecha, autor y mensaje.
- Calcula los ficheros modificados en ese commit y muestra hasta diez rutas.
- Analiza el reflog local para encontrar nombres y commits que podrían corresponder a ramas eliminadas.
- Guarda y actualiza los resultados en `git_branches.db`.
- Busca en los registros por nombre de rama, ruta del repositorio o fichero; incluye búsqueda por lotes de ramas o ficheros.
- Copia filas y exporta resultados a Excel.
- **Últimas versiones**: localiza, entre todas las ramas, dónde está la versión más reciente de cada fichero, la lista y la descarga a una carpeta local; permite guardar búsquedas y sincronizarlas automáticamente.

## Últimas versiones de ficheros entre ramas

En la pestaña **Últimas versiones**, el flujo principal se organiza en **Explorar y descargar**; las búsquedas y sincronizaciones guardadas están separadas en su propia pestaña:

1. Elige el ámbito (ramas remotas, locales o todas) y, opcionalmente, una expresión regular para las rutas de fichero (por ejemplo, `\.py$` o `^src/.*\.(cs|xml)$`) y otra para los nombres de rama.
2. **Escanear ramas** muestra cada fichero con la rama en la que se modificó más recientemente (según la fecha del último commit que lo tocó), el commit, el autor, las ramas donde el contenido es idéntico y en cuántas ramas existe.
3. Marca ficheros haciendo clic en `☐`, con la tecla Espacio, con **Marcar por regex** o con **Marcar todo**.
4. **Descargar marcados** o **Descargar todos** copia esa versión a la carpeta destino, con la misma estructura que el repositorio o con una subcarpeta por rama. El listado también se puede exportar a Excel.
5. **Guardar búsqueda...** almacena el filtro completo (incluye ficheros que aparezcan después) o solo los ficheros marcados, y opcionalmente activa la descarga automática cada N minutos.

Para revisar los ficheros que ya hay en una carpeta, indica el destino y pulsa **Comprobar estado local**. La columna **Estado local** muestra si están al día, si hay una actualización disponible, si se modificaron localmente, si no están descargados o si no tienen registro en el manifiesto. Si están al día, guarda la búsqueda para actualizarlos automáticamente; también puedes usar **Ejecutar ahora** en búsquedas guardadas o descargar de nuevo los ficheros seleccionados. Los cambios locales no se sobrescriben salvo que se active esa opción.

La tabla principal muestra solo selección, fichero, rama más reciente y estado local para facilitar la lectura. **Ver detalles**, el doble clic o el menú contextual muestran fecha, commit, autor, mensaje y ramas con contenido idéntico; copiar o exportar mantiene todos esos datos. Pasa el cursor por controles y tabla para consultar la ayuda de cada opción.

La sincronización ejecuta `git fetch --all --prune`, compara las puntas de las ramas con la ejecución anterior y solo escanea y descarga si algo cambió. En la carpeta destino se guarda `.git_latest_manifest.json` para descargar únicamente los ficheros que cambian. Los ficheros modificados localmente no se sobrescriben salvo que se active esa opción. Se copia el contenido tal cual está en Git, sin filtros de fin de línea ni LFS.

La descarga automática funciona mientras la aplicación está abierta. Para ejecutarla sin abrir la interfaz, por ejemplo desde el Programador de tareas de Windows:

~~~powershell
python main.py --list                 # búsquedas guardadas
python main.py --sync "Mi búsqueda"   # una búsqueda (nombre o id)
python main.py --sync-all             # todas las que tienen descarga automática
python main.py --sync-all --force     # sin comprobar si las ramas cambiaron
python main.py --db C:\ruta\git_branches.db --sync-all
~~~

Si se ejecuta desde otra carpeta, indica `--db` con la misma base de datos que usa la interfaz.

## Estructura del código

~~~text
main.py                  Punto de entrada (GUI o CLI)
git_info/cli.py          Argumentos de línea de comandos y sincronización sin interfaz
git_info/core/           Lógica de la aplicación, sin Tkinter
  gitcmd.py              Ejecución de git y utilidades comunes
  commit_info.py         Datos de commits (GitPython)
  branch_scanner.py      Ramas remotas y candidatas recuperables del reflog
  branch_store.py        Historial SQLite de ramas y consultas
  formatting.py          Textos de informes y detalles
  excel.py               Exportación genérica a XLSX
  latest_scan.py         Última versión de cada fichero entre ramas
  exporter.py            Descarga a carpeta local y manifiesto
  saved_searches.py      Búsquedas guardadas (SQLite)
  sync.py                Ejecución y detección de cambios de búsquedas guardadas
git_info/gui/            Interfaz Tkinter
  app.py                 Ventana principal
  console_tab.py, search_tab.py, batch_tab.py, latest_tab.py   Pestañas
  saved_searches_panel.py, dialogs.py, widgets.py, background.py  Componentes reutilizables
~~~

## Recuperación: cómo funciona

La aplicación **no recrea ni cambia ramas automáticamente**. Para cada candidato encontrado en el reflog muestra los comandos `git branch` y `git checkout` que puedes revisar y ejecutar manualmente.

La detección depende de que el reflog y los objetos de commit sigan disponibles en el repositorio local. Un candidato es una sugerencia que conviene verificar antes de usar.

## Uso

Requisitos: Python 3.8 o posterior, Git instalado y disponible en el `PATH`, y Tkinter. Está preparado principalmente para uso de escritorio en Windows.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
~~~

También se puede usar `CreateEnv.bat`, pero **si ya existe, elimina y vuelve a crear la carpeta `.venv`**. Usa los comandos manuales si quieres conservar ese entorno.

## Qué ocurre al analizar un repositorio

La aplicación ejecuta un `fetch --prune` para cada remoto configurado y luego lista las referencias del remoto predeterminado. Esto necesita acceso de red y actualiza/prunea las referencias remotas locales obsoletas del repositorio analizado; no borra ramas del servidor remoto.

La base de datos `git_branches.db` se crea en el directorio de trabajo desde el que se inicia la aplicación. Mantiene una fila por repositorio, nombre y tipo de rama, y actualiza los datos del último commit detectado. No es un historial completo de todos los commits.

La base almacena rutas locales, nombres de rama, hashes, autores, mensajes y nombres de ficheros modificados, además de las búsquedas guardadas (tabla `saved_searches`). Revísala antes de compartirla.

## Dependencias principales

- GitPython para consultar Git y sus remotos.
- Tkinter para la interfaz gráfica.
- SQLite (`sqlite3`) para el registro local.
- openpyxl para exportar a Excel.

~~~