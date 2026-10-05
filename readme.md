# Git Branch Info & Recovery

![Estado](https://img.shields.io/badge/estado-En%20desarrollo-yellow)
![Versión](https://img.shields.io/badge/versión-V26.09.028-blue)
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

También se puede ejecutar `CreateEnv.bat`, pero ese script vuelve a crear el
entorno `.venv`. Utiliza los comandos manuales si necesitas conservarlo.

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
los commits solo mediante **fast-forward**. No cambia de rama, no publica
commits, ni hace stash, reset o merge de historiales divergentes. Se bloquea
si la rama elegida no está activa (incluido HEAD separado), hay cambios
locales, ficheros sin seguimiento, commits locales pendientes u operaciones
Git en curso. Los ficheros ignorados tampoco se sobrescriben por una descarga.
Un fallo de conexión no se trata como «al día» ni se usan referencias antiguas
para actualizar. El resultado y los commits anterior/remoto/final se guardan
en SQLite.

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
```

El código 1 indica errores de ejecución, fallos de descarga o una actualización
de repositorio bloqueada. El código 2 indica una búsqueda o automatización
inexistente. `--force` solo afecta al escaneo de búsquedas; nunca permite
sobrescribir trabajo local ni omitir la seguridad de los repositorios.
`--sync-all` conserva su comportamiento: ejecuta únicamente búsquedas guardadas.

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
git_info/
├── cli.py                       Entrada CLI y sincronización sin GUI
├── core/
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
│   └── sync.py                  Sincronización incremental
└── gui/
    ├── app.py                   Ventana principal
    ├── automations_tab.py       Vista de automatizaciones por carpeta o global
    ├── latest_tab.py            Exploración y descarga de versiones
    ├── search_tab.py            Búsqueda en SQLite
    ├── batch_tab.py             Consultas por lotes
    └── ...                      Diálogos, widgets y tareas en segundo plano
tests/
├── test_automations_gui.py
├── test_exporter_status.py
├── test_latest_scan.py
├── test_repo_automations.py
└── test_saved_search_details.py
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
- La sincronización automática integrada requiere que la GUI permanezca
  abierta; para ejecución desatendida debe usarse la CLI.

## Licencia

El proyecto declara licencia GPL en sus metadatos internos.
