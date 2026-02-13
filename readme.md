
# Git Branch Info & Recovery

Descripción
-----------
Esta aplicación de escritorio (Tkinter) ayuda a inspeccionar y recuperar ramas de repositorios Git locales. Escanea un repositorio, recopila información de ramas (locales y remotas), busca ramas recuperables en el reflog, y mantiene un historial en una base de datos SQLite para búsquedas, auditoría y recuperación posterior.

Principales características
--------------------------
- Interfaz gráfica con `Tkinter` para seleccionar repositorios y ver resultados.
- Obtención de ramas remotas y locales con detalles de último commit (hash, autor, fecha, mensaje).
- Detección de ramas potencialmente recuperables usando el `reflog`.
- Registro/actualización de la información en una base de datos SQLite (`git_branches.db`).
- Búsqueda interactiva y filtros por rama, repositorio y archivos modificados.
- Búsqueda en lote (pegar múltiples nombres de ramas o archivos).
- Exportación de resultados a Excel (`openpyxl`).
- Copiar filas/selecciones y ver detalles de commits desde la GUI.

Archivos importantes
-------------------
- `CreateEnv.bat` — (opcional) script de creación/ajuste de entorno en Windows.
- `main.py` — aplicación principal (interfaz y lógica). Ejecuta la GUI y usa `gitpython`, `openpyxl` y `sqlite3`.

Requisitos
---------
- Python 3.8 o superior.
- Dependencias Python (puedes instalarlas manualmente si `CreateEnv.bat` no lo hace):

```powershell
pip install gitpython openpyxl
```

Uso (Windows)
-------------
1. Abre PowerShell o CMD en la carpeta del proyecto.
2. (Opcional) Ejecuta `CreateEnv.bat` si quieres que prepare el entorno.

```powershell
.\CreateEnv.bat
```

3. Ejecuta la aplicación:

```powershell
python main.py
```

Comportamiento y salida
-----------------------
- La aplicación crea/usa la base de datos `git_branches.db` en la carpeta del proyecto para almacenar el historial de ramas.
- Permite exportar resultados a un archivo Excel cuando se solicita.
- Revisa la consola dentro de la aplicación para mensajes y progreso.

Notas de seguridad y buenas prácticas
-----------------------------------
- Revisa el contenido de `CreateEnv.bat` antes de ejecutarlo.
- Ejecuta la aplicación en un entorno virtual si lo deseas para aislar dependencias.

Contacto
-------
Si quieres mejoras (por ejemplo, integración con servicios remotos o automatizaciones), abre un issue o comparte detalles del cambio deseado.

