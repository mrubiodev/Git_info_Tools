# Git Branch Info & Recovery

![Estado](https://img.shields.io/badge/estado-En%20desarrollo-yellow)
![Versión](https://img.shields.io/badge/versión-V26.10.029-blue)
![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)
![Git](https://img.shields.io/badge/Git-requerido-F05032?logo=git&logoColor=white)
![Tkinter](https://img.shields.io/badge/GUI-Tkinter-444444)
![SQLite](https://img.shields.io/badge/datos-SQLite-003B57?logo=sqlite&logoColor=white)

Aplicación de escritorio para explorar ramas Git, localizar la versión más
reciente de cada fichero, recorrer su historial por ramas y recuperar
referencias de ramas eliminadas a partir del reflog.

Los resultados se pueden buscar, exportar a Excel y guardar en SQLite. Las
versiones seleccionadas también pueden descargarse de forma incremental y
segura a otra carpeta.

## Características principales

- Consulta ramas **locales y remotas**, incluidos commits locales todavía no
  publicados con `push`.
- Localiza qué rama contiene la versión más reciente de cada fichero.
- Distingue entre un cambio real y un fichero simplemente heredado al crear
  una rama.
- Muestra un árbol del historial del fichero, agrupado por ramas y commits.
- Filtra ramas y rutas mediante expresiones regulares.
- Descarga ficheros conservando la estructura del repositorio o separándolos
  por rama.
- Protege modificaciones locales mediante un manifiesto de descargas.
- Guarda búsquedas y permite sincronizarlas desde la GUI o la línea de
  comandos.
- Mantiene repositorios completos actualizados desde una rama remota mediante
  fast-forward, con automatizaciones configurables por carpeta y una vista global.
- Exporta e importa automatizaciones en JSON para compartirlas.
- Pide la passphrase de claves SSH cifradas cuando el fetch falla por
  autenticación y la mantiene en un `ssh-agent` de la sesión.
- Incluye una **versión Lite** (`main_lite.py`) solo con las automatizaciones,
  pensada para dejarla abierta como planificador.
- Registra ramas y resultados en SQLite.
- Busca posibles ramas eliminadas utilizando el reflog local.
- Copia resultados y los exporta a Excel.

## Inicio rápido

### Requisitos

- Python 3.8 o posterior.
- Git instalado y disponible en `PATH`.
- Tkinter, incluido normalmente con Python en Windows.

### Instalación

```powershell
git clone https://github.com/mrubiodev/Git_info_Tools.git
Set-Location Git_info_Tools

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Para abrir solo la gestión de automatizaciones: `python main_lite.py`
(ver [Versión Lite](#versión-lite-solo-automatizaciones)).

También se puede ejecutar `CreateEnv.bat`, pero ese script vuelve a crear el
entorno `.venv`. Utiliza los comandos manuales si necesitas conservarlo.

## Novedades V26.10.029

- **Credenciales SSH**: si `fetch` falla con `Permission denied (publickey)`
  porque la clave tiene passphrase, la GUI la pide, la carga en un `ssh-agent`
  de sesión y reintenta. Botón **Credenciales SSH...** en Automatizaciones; la
  CLI la pide por consola si hay terminal interactiva.
- **Versión Lite**: `main_lite.py` / `--lite` y `empaquetar_lite.bat`.

## Flujo recomendado

1. Indica la ruta de un repositorio Git.
2. Abre **Últimas versiones**.
3. Mantén el ámbito **Todas** para incluir ramas locales y remotas.
4. Aplica filtros opcionales y pulsa **Escanear ramas**.
5. Revisa la rama, el commit y el estado de cada fichero.
6. Abre **Historial por ramas** para inspeccionar su evolución.
7. Marca los ficheros necesarios y descárgalos o guarda la búsqueda.

> [!IMPORTANT]
> El ámbito **Remotas** solo analiza referencias como `origin/main` o
> `origin/feature`. Un commit recién creado no aparecerá ahí hasta hacer
> `push`. Usa **Todas** para detectar también commits locales.

## Últimas versiones de ficheros

La pestaña **Últimas versiones** compara los ficheros que existen en la punta
de las ramas seleccionadas.

Para cada ruta:

1. Obtiene el blob presente en cada rama.
2. Busca el último commit que modificó esa ruta dentro de cada historial.
3. Compara las fechas de esos commits.
4. Selecciona la rama con el cambio más reciente.

Si una rama nueva contiene exactamente el mismo blob y el mismo último commit
que la rama principal, el fichero se atribuye a `main` o `master`. Crear una
rama no se considera una modificación del fichero.

### Ámbitos de ramas

| Ámbito | Incluye | Uso recomendado |
|---|---|---|
| **Todas** | Ramas locales y remotas | Trabajo diario y commits sin `push` |
| **Locales** | `refs/heads/*` | Revisar únicamente el estado local |
| **Remotas** | `refs/remotes/*` | Revisar solo lo publicado o descargado del remoto |

La opción **Hacer fetch antes** ejecuta `git fetch --all --prune` para
actualizar las referencias remotas. No publica commits ni elimina ramas del
servidor.

### Filtros

Los filtros de rama y fichero aceptan expresiones regulares:

| Objetivo | Ejemplo |
|---|---|
| Ficheros Python | `\.py$` |
| Carpeta `src` | `^src/` |
| XML dentro de `config` | `^config/.*\.xml$` |
| Ramas feature | `(^|/)feature/` |
| `main` local o remota | `(^|/)main$` |

La opción **Ignorar mayúsculas** controla si las expresiones distinguen entre
mayúsculas y minúsculas.

### Información disponible

La tabla principal muestra:

- selección;
- ruta del fichero;
- rama con la versión más reciente;
- estado de la copia local.

**Ver detalles**, el doble clic y el menú contextual añaden:

- fecha del último cambio;
- hash del commit;
- autor y mensaje;
- ramas con contenido idéntico;
- número de ramas donde existe el fichero.

### Historial por ramas

Selecciona un fichero y pulsa **Historial por ramas** para abrir un árbol con:

- las ramas analizadas;
- la rama principal identificada;
- los commits que modificaron la ruta;
- fecha, hash, autor y mensaje de cada cambio.

El árbol representa el historial alcanzable desde cada rama. Por ello, un
commit común anterior a la bifurcación puede aparecer bajo varias ramas.

## Descarga segura

Los resultados pueden guardarse:

- con la misma estructura de carpetas que el repositorio; o
- dentro de una subcarpeta por rama.

La aplicación crea `.git_latest_manifest.json` en la carpeta destino. Este
manifiesto permite comparar la versión descargada, la versión disponible y el
contenido actual del disco.

### Estados locales

| Estado | Significado |
|---|---|
| **Al día** | El contenido local coincide con la versión seleccionada |
| **Actualización disponible** | Hay una versión nueva y la copia anterior no fue modificada |
| **Modificado localmente** | El fichero cambió después de descargarlo |
| **No descargado** | El fichero todavía no existe en el destino |
| **Sin seguimiento** | Existe, pero no figura en el manifiesto |
| **Error** | No se pudo leer o comparar el fichero |

Por defecto, los ficheros modificados localmente **no se sobrescriben**.
Activa **Sobrescribir ficheros modificados localmente** solo si deseas
reemplazarlos deliberadamente.

El contenido se extrae directamente del objeto Git. No se aplican filtros del
working tree, conversiones de fin de línea ni materialización de Git LFS.

## Búsquedas guardadas y sincronización

Una búsqueda guardada conserva:

- repositorio y ámbito de ramas;
- filtros de ramas y ficheros;
- selección completa o rutas marcadas;
- carpeta y estructura de destino;
- política de sobrescritura;
- política ante fallos de fetch (`stop` o `local`);
- intervalo de sincronización automática.

La sincronización compara la huella de las puntas de las ramas. Si no hay
cambios, evita repetir el escaneo y la descarga.

En **Búsquedas guardadas**, selecciona una búsqueda y pulsa **Ejecutar ahora**
para forzar su ejecución cuando quieras, aunque las ramas no hayan avanzado.
La tabla compacta muestra nombre, repositorio, activación automática, fecha y
resultado breve. Con doble clic, **Ver detalles** o clic derecho puedes abrir
la última ejecución: cada fichero descargado indica su ruta de destino, ruta
original, rama y commit. Allí también aparecen ficheros sin cambios, conflictos
locales, rutas ausentes, avisos y errores completos. Estos detalles se guardan
en SQLite y también están disponibles después de una ejecución automática o
desde la CLI; al volver a ejecutar se sustituyen por los de la última ejecución.

La sincronización automática de la GUI funciona mientras la aplicación está
abierta. Para usar el Programador de tareas de Windows o cualquier otro
automatismo, utiliza la CLI.

## Automatizaciones de repositorios

La pestaña **Automatizaciones** reúne las actualizaciones de repositorios y las
búsquedas guardadas existentes. **Carpeta seleccionada** muestra las tareas del
repositorio indicado en la barra superior y de repositorios dentro de esa
carpeta. **Todas** muestra también las de otras ubicaciones. El filtro solo
afecta a la vista: las automatizaciones ocultas siguen funcionando.

Pulsa **Añadir repositorio** para elegir una carpeta, nombre, rama local,
remoto y rama remota. **Leer ramas y seguimiento** propone el seguimiento Git
existente; puedes configurar un origen diferente. El intervalo inicial es
**15 minutos**, editable entre 1 y 1440 minutos. Añade una tarea por cada
repositorio; se impiden duplicados de nombre o carpeta. Puedes editarla,
pausarla, ejecutarla manualmente, consultar detalles o eliminarla sin borrar
los ficheros del repositorio.

Cada ejecución descarga la rama remota configurada con `fetch` e incorpora
los commits solo mediante **fast-forward** (el equivalente a un pull sin crear
un commit de merge). **Nunca crea commits de rama ni hace push**, reset,
cambio de rama o merge de historiales divergentes. Los hooks de merge se
desactivan en esta operación para evitar acciones automáticas externas.
Se bloquea si la rama elegida no está activa (incluido HEAD separado), hay
commits locales pendientes, conflictos sin resolver u operaciones Git en curso.
Los ficheros ignorados tampoco se sobrescriben por una descarga.
Un fallo de conexión nunca se trata como «al día». El resultado y los commits
anterior/de referencia/final se guardan en SQLite.

### Si falla fetch (repositorios y búsquedas guardadas)

Elige **Si falla fetch** al crear/editar una tarea o con el botón del mismo
nombre en **Automatizaciones** y **Búsquedas guardadas**:

- **Detener (`stop`, predeterminado)**: no escanea, descarga, crea stash ni
  incorpora commits después del fallo. Las tareas existentes y los JSON antiguos
  sin esta opción pasan también a `stop`; las búsquedas ya no continúan por defecto.
- **Continuar (`local`)**: autoriza explícitamente el uso de referencias locales
  posiblemente obsoletas. En repositorios solo permite fast-forward hacia el
  commit de la referencia remota configurada que existía **antes** de intentar
  fetch. Si esa referencia no existe, falla: no cambia a otro remoto ni a `FETCH_HEAD`.
  Conserva todas las protecciones de rama activa, divergencia, trabajo local y stash.
  En búsquedas puede escanear/descargar según las referencias disponibles localmente.

El resultado comienza con **REMOTO NO ACTUALIZADO**, incluso si no hay cambios
locales o si la descarga/fast-forward termina. El error original y los avisos se
guardan en los detalles, también si falla una operación posterior. Nunca confirma
que el servidor esté al día. Si la búsqueda tiene **Hacer fetch antes** desactivado,
esta política no interviene: no se intenta contactar con el remoto.

#### Credenciales SSH (clave con passphrase)

La aplicación ejecuta Git sin consola, así que `ssh` no puede pedir la passphrase
de una clave cifrada y el fetch falla con `Permission denied (publickey)`. Cuando
ocurre, la GUI pide la passphrase, la carga en un `ssh-agent` propio de la sesión
(el de Git for Windows, con las claves `~/.ssh/id_*`) y reintenta la operación. La
passphrase solo queda en memoria; el agente se cierra al salir. Si cancelas, las
ejecuciones automáticas no vuelven a preguntar: usa **Credenciales SSH...** en
**Automatizaciones**. En la CLI se pide por consola si hay terminal interactiva;
en el Programador de tareas, carga la clave en un agente o usa una clave sin passphrase.

En **Editar**, elige la política de **Cambios locales**:

| Política | Comportamiento |
|---|---|
| **Sincronizar conservando cambios locales** | Incorpora lo nuevo sin preguntar, conservando cambios preparados, no preparados y ficheros sin seguimiento cuando Git lo permite. Si necesita sobrescribir trabajo local, se bloquea sin descartarlo. No hace stash. |
| **Guardar cambios locales en stash y actualizar** | Guarda cambios preparados/no preparados y ficheros sin seguimiento antes del fast-forward. Puedes dejarlos guardados para recuperación manual o activar **Reaplicar automáticamente el stash**. |
| **Bloquear si hay cambios locales** | Mantiene la protección anterior: no descarga si hay cambios o ficheros sin seguimiento. |

Las nuevas tareas proponen **Sincronizar**; las existentes conservan **Bloquear**
hasta que las edites. La sincronización directa es conservadora: Git puede
bloquear cambios locales en un fichero que también cambia en el remoto aunque
estén en líneas diferentes. Para combinar ese trabajo, utiliza stash con
reaplicación. Stash crea objetos internos de respaldo de Git, no commits en
la rama ni publicaciones al servidor. No incluye ficheros ignorados ni trabajo
dentro de submódulos; si estos tienen cambios, el modo stash se bloquea.
Si no hay novedades remotas, no se crea ningún stash.

Si falla la actualización después de guardar el stash, se intenta restaurar
el trabajo original. Si falla la reaplicación, se conserva el stash y se muestra
el error junto con su SHA; pueden quedar cambios parcialmente aplicados o
conflictos en la carpeta. No se repite la operación mientras quede ese trabajo:
resuelve el problema y, para reanudar con cambios locales, vuelve a guardar la
configuración. Los conflictos Git sin resolver siempre bloquean. Los stashes
anteriores no se eliminan. Los detalles indican el stash creado; para recuperarlo
manualmente usa `git stash apply --index <SHA>` y elimina su entrada solo después
de comprobar que el trabajo está recuperado.

### Compartir automatizaciones

Selecciona varias filas con **Ctrl/Mayús** y pulsa **Exportar seleccionadas**.
El JSON versionado incluye solo la configuración de las tareas elegidas,
tanto repositorios como búsquedas guardadas: no exporta identificadores de
SQLite, historial de ejecuciones, resultados ni contenido del repositorio.
Incluye rutas locales y filtros: revisa el archivo antes de compartirlo.

Con **Importar...**, abre el JSON y selecciona las tareas deseadas en la vista
previa. El doble clic o **Ajustar seleccionada** permite cambiar nombre, rutas,
intervalo y activación; en repositorios también ramas, remoto, política de
cambios locales y reaplicación del stash. Incluye la política `fetch_failure`
para ambos tipos; si falta en un JSON versión 1, se usa `stop`. La vista de
ajustes permite cambiarla antes de importar. Por defecto se conservan las rutas
y la activación originales: **las tareas automáticas pueden ejecutarse en la
siguiente revisión del planificador**. Comprueba la configuración antes de aceptar.
Las rutas de repositorio deben existir en el equipo receptor.
No se reemplazan duplicados por nombre (del mismo tipo) ni por carpeta de
repositorio: cambia el nombre/ruta o desmarca la tarea. La importación es
atómica: si una tarea no es válida, no se guarda ninguna. Cancelar no cambia
la base de datos. Puedes editar los filtros de búsquedas desde su vista habitual.

La aplicación revisa las tareas cada 30 segundos, con primera revisión a los
5 segundos, y ejecuta las que han cumplido su intervalo. **Ejecutar ahora**
no espera al intervalo y no omite las protecciones. Las tareas pausadas solo
se ejecutan por petición manual. La GUI debe permanecer abierta; para
ejecución desatendida programa `python main.py --update-repos` en Windows.
La CLI ejecuta una pasada y termina; la frecuencia la establece el programador
externo. Usa la misma ruta `--db` que en la GUI.

Las ejecuciones de esta función se excluyen entre sí mediante un bloqueo del
sistema operativo en los metadatos Git, también entre GUI/CLI y worktrees
del mismo repositorio. Esto no bloquea comandos Git de otras herramientas:
evita trabajar sobre una carpeta mientras se actualiza. Se vuelve a comprobar
el estado local después de descargar y antes de incorporar los commits.
No se actualizan automáticamente los repositorios de submódulos ni se
materializa Git LFS explícitamente; se aplica el comportamiento de checkout
y los filtros configurados en Git.

### Versión Lite (solo automatizaciones)

Para dejar la aplicación abierta solo como planificador, usa la GUI ligera:

```powershell
python main_lite.py            # equivalente a: python main.py --lite
python main_lite.py --db C:\datos\git_branches.db
```

Muestra únicamente **Automatizaciones** (repositorios y búsquedas guardadas) y
una **Consola** con el registro. Permite añadir, editar, ejecutar, activar/pausar,
cambiar intervalo y política de fetch, eliminar, importar/exportar e introducir
**Credenciales SSH**. Usa la misma base SQLite que la versión completa y ejecuta
el mismo planificador. Los filtros y el destino de una búsqueda guardada se
editan en la versión completa. Para generar el EXE: `empaquetar_lite.bat`
(mismos argumentos que `empaquetar.bat`; crea `<Proyecto>_Lite.exe`).
No abras a la vez la versión completa y la Lite con auto activado sobre la misma
base: ambas ejecutarían el planificador.

## Línea de comandos

```powershell
# Listar búsquedas guardadas
python main.py --list

# Ejecutar una búsqueda por nombre o identificador
python main.py --sync "Mi búsqueda"

# Se puede repetir --sync
python main.py --sync "Backend" --sync "Configuración"

# Ejecutar todas las búsquedas con sincronización automática
python main.py --sync-all

# Forzar el escaneo aunque las referencias no hayan cambiado
python main.py --sync-all --force

# Usar otra base SQLite
python main.py --db C:\datos\git_branches.db --sync-all

# Activar el escaneo paralelo experimental
python main.py --parallel --workers 8 --sync-all

# Listar todas las automatizaciones (repositorios y búsquedas)
python main.py --list-automations

# Actualizar un repositorio por nombre o id; se puede repetir
python main.py --update-repo "Mi repositorio"

# Actualizar todos los repositorios con auto activado
python main.py --update-repos

# Ejecutar ambos tipos de automatización en una pasada
python main.py --update-repos --sync-all

# Autorizar referencias posiblemente obsoletas solo para esta pasada (no cambia SQLite)
python main.py --update-repo "Mi repositorio" --sync "Mi búsqueda" --fetch-failure local

# Exigir detenerse en esta pasada aunque las tareas tengan configurado continuar
python main.py --update-repos --sync-all --fetch-failure stop

# Abrir la GUI Lite (solo automatizaciones); equivale a python main_lite.py
python main.py --lite
```

El código 1 indica errores de ejecución, fallos de fetch (incluso si se continuó
con referencias locales), fallos de descarga o una actualización
de repositorio bloqueada. El código 2 indica una búsqueda o automatización
inexistente. `--force` solo afecta al escaneo de búsquedas; nunca permite
sobrescribir trabajo local ni omitir la seguridad de los repositorios.
`--sync-all` conserva su comportamiento: ejecuta únicamente búsquedas guardadas.
Si un fetch falla por una clave SSH con passphrase y hay terminal interactiva,
la CLI pide la passphrase una vez (hasta 3 intentos) y reintenta; sin terminal
el fallo se informa con código 1.

## Análisis y recuperación de ramas

El botón **Obtener Información y Registrar**:

1. ejecuta `fetch --prune` en los remotos configurados;
2. obtiene el último commit de cada rama remota;
3. registra hash, fecha, autor, mensaje y ficheros modificados;
4. analiza el reflog local buscando referencias a ramas que ya no existen.

La aplicación **no crea, elimina ni cambia ramas automáticamente**. Para cada
candidato recuperable muestra comandos que deben revisarse y ejecutarse
manualmente.

La recuperación depende de que el reflog y el objeto del commit sigan
disponibles. Git puede eliminar objetos inalcanzables durante sus tareas de
mantenimiento, por lo que un candidato no garantiza que la rama sea
recuperable indefinidamente.

## Base de datos

La ruta predeterminada es:

```text
%USERPROFILE%\.git_branch_info\git_branches.db
```

Puede cambiarse con `--db`. La base contiene:

- repositorios y ramas analizadas;
- metadatos del último commit registrado;
- ficheros modificados;
- búsquedas guardadas y resultados de sincronización;
- automatizaciones de repositorios, su configuración y última ejecución;
- caché de árboles asociada a commits inmutables.

La tabla de ramas conserva el último estado conocido por repositorio, nombre y
tipo de rama. No sustituye al historial de commits de Git.

La base puede contener rutas locales, autores y mensajes de commit. Revísala
antes de compartirla.

### Icono del ejecutable y las ventanas

El empaquetado incorpora `res/app_icon.ico` tanto como icono del EXE como
recurso interno para las ventanas Tkinter. La GUI usa ese recurso también
en modo PyInstaller y define su identidad de aplicación en Windows para
la barra de tareas. El ICO incluye tamaños de 16, 32, 48, 64 y 256 píxeles.
Si el Explorador conserva un icono antiguo después de
reemplazar el EXE, comprueba una copia con otro nombre: puede ser su caché
de iconos, no el contenido del ejecutable.

### Protección frente a fugas de datos

El repositorio ignora bases SQLite, manifiestos de descargas, ficheros `.env`,
claves privadas, metadatos locales de análisis y nuevos ZIP de `release/`.
El script de empaquetado cancela la creación del ZIP si detecta esos archivos
en `dist/`. La configuración PyInstaller usa rutas relativas en lugar de rutas
locales del desarrollador; el empaquetado no ejecuta `pip freeze` ni copia al
ZIP las dependencias instaladas en tu entorno. No fuerces la inclusión de ficheros ignorados con
`git add -f`; antes de publicar, revisa `git status` y el contenido del ZIP.
Un archivo que ya estuvo publicado en Git puede permanecer accesible en el
historial aunque se deje de versionar; esta protección evita futuras
publicaciones, pero no reescribe commits anteriores.

## Estructura del proyecto

```text
main.py
main_lite.py                     GUI ligera (solo automatizaciones)
git_info/
├── cli.py                       Entrada CLI y sincronización sin GUI
├── core/
│   ├── automation_transfer.py   Exportación/importación JSON de automatizaciones
│   ├── branch_scanner.py        Ramas remotas y candidatos del reflog
│   ├── branch_store.py          Persistencia y consultas SQLite
│   ├── commit_info.py           Metadatos de commits
│   ├── excel.py                 Exportación XLSX
│   ├── exporter.py              Descarga segura y manifiesto
│   ├── gitcmd.py                Ejecución de comandos Git
│   ├── latest_scan.py           Versiones e historial por fichero
│   ├── repo_cache.py            Caché por repositorio y commit
│   ├── repo_automations.py      Actualización segura y persistencia de repositorios
│   ├── saved_searches.py        Persistencia de búsquedas
│   ├── ssh_auth.py              ssh-agent de sesión para claves con passphrase
│   └── sync.py                  Sincronización incremental
└── gui/
    ├── app.py                   Ventana principal
    ├── lite_app.py              Ventana Lite: solo automatizaciones
    ├── credentials.py           Petición de passphrase SSH y reintento
    ├── automations_tab.py       Vista de automatizaciones por carpeta o global
    ├── latest_tab.py            Exploración y descarga de versiones
    ├── search_tab.py            Búsqueda en SQLite
    ├── batch_tab.py             Consultas por lotes
    └── ...                      Diálogos, widgets y tareas en segundo plano
tests/
├── test_automation_transfer.py
├── test_automations_gui.py
├── test_exporter_status.py
├── test_latest_scan.py
├── test_lite_app.py
├── test_repo_automations.py
├── test_saved_search_details.py
└── test_ssh_auth.py
```

La lógica de `git_info/core` no depende de Tkinter y puede reutilizarse desde
la GUI, la CLI o pruebas automatizadas.

## Desarrollo

Ejecutar las pruebas:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Comprobar que todos los módulos compilan:

```powershell
.\.venv\Scripts\python.exe -m compileall -q git_info tests
```

## Dependencias principales

- [GitPython](https://gitpython.readthedocs.io/) para operaciones Git de alto
  nivel.
- Tkinter para la interfaz gráfica.
- `sqlite3` de la biblioteca estándar para persistencia local.
- [openpyxl](https://openpyxl.readthedocs.io/) para exportación XLSX.
- [PyInstaller](https://pyinstaller.org/) para generar el ejecutable de
  Windows.

## Limitaciones conocidas

- El historial depende de los commits disponibles en el clon; un clon
  superficial puede ofrecer información incompleta.
- La comparación usa la fecha de commit registrada por Git.
- Los renombrados se tratan como rutas distintas durante el escaneo de últimas
  versiones.
- El escaneo paralelo es experimental.
- La sincronización automática integrada requiere que la GUI (completa o Lite)
  permanezca abierta; para ejecución desatendida debe usarse la CLI.
- En ejecución desatendida no se puede pedir la passphrase SSH: usa un agente
  con la clave cargada o una clave sin passphrase.
- La passphrase introducida en la GUI solo dura la sesión; al cerrar la
  aplicación se detiene su `ssh-agent`.
- `test_repo_automations.py` usa repositorios Git reales y tarda varios minutos.

## Licencia

El proyecto declara licencia GPL en sus metadatos internos.
