"""Textos y etiquetas legibles para mostrar la información de ramas."""

TYPE_SHORT = {"remote_existing": "Remota", "local_existing": "Local", "reflog_recoverable": "Recuperable"}
TYPE_LONG = {"remote_existing": "Remota Existente", "local_existing": "Local Existente",
             "reflog_recoverable": "Recuperable (Reflog)"}
STATUS_TEXT = {"new": "NUEVA", "updated_commit": "ACTUALIZADA", "seen": "VISTA"}


def type_short(branch_type):
    return TYPE_SHORT.get(branch_type, branch_type)


def status_text(status):
    return STATUS_TEXT.get(status, status if status else "")


def truncate(text, length):
    text = text or ""
    return text[:length] + "..." if len(text) > length else text


def repo_short_name(repo_path):
    return repo_path.split('\\')[-1] if '\\' in repo_path else repo_path.split('/')[-1]


def recovery_commands(branch_name, commit_hash):
    return [f'git branch "{branch_name}" {commit_hash}',
            f'git checkout "{branch_name}"',
            f'git push -u origin "{branch_name}"']


def format_branch_report(branches, title, recoverable=False):
    """Lista de bloques de texto para la consola con el resumen de ramas."""
    blocks = [f"\n--- {title} ---"]
    if not branches:
        blocks.append(f"No se encontraron {title.lower()} o no se pudo obtener su información.")
        return blocks

    branches.sort(key=lambda x: x['date'], reverse=True)
    lines = [f"{'Rama':<40} {'Hash':<8} {'Fecha Último Commit':<20} {'Estado DB':<12} {'Mensaje del Commit':<40}",
             "-" * 130]
    for info in branches:
        state = STATUS_TEXT.get(info.get('status'), "VISTA")
        message = info['message'][:37] + '...' if len(info['message']) > 40 else info['message']
        lines.append(f"{info['name']:<40} {info['hash']:<8} {info['date']:<20} {state:<12} {message:<40}")
    blocks.append("\n".join(lines))

    if recoverable:
        blocks.append("\nComandos para recuperar las ramas marcadas como 'NUEVA' o 'ACTUALIZADA':")
        blocks.append("=" * 100)
        for info in branches:
            if info.get('status') in ('new', 'updated_commit'):
                branch_cmd, checkout_cmd, push_cmd = recovery_commands(info['name'], info['hash'])
                blocks += [f"Rama: {info['name']}",
                           f"  Último commit conocido: {info['hash']}",
                           "  Comandos para recuperar:",
                           f"    {branch_cmd}",
                           f"    {checkout_cmd}",
                           f"    {push_cmd}  (Opcional: para subirla al remoto)",
                           "-" * 50]
        blocks.append("=" * 100)
        blocks.append("\nNota: Revisa cada rama recuperada antes de subirla al remoto.")
    return blocks


def format_branch_details(d):
    """Texto de la ventana de detalles a partir de BranchStore.get_details()."""
    sep, sub = '=' * 80, '─' * 80
    text = f"""
{sep}
DETALLES DE LA RAMA
{sep}

Nombre de la Rama: {d['branch_name']}
Tipo: {TYPE_LONG.get(d['branch_type'], d['branch_type'])}
Estado: {status_text(d['status'])}

{sub}
INFORMACIÓN DEL COMMIT
{sub}

Hash del Commit: {d['last_commit_hash']}
Fecha del Commit: {d['commit_date']}
Autor: {d['commit_author']}
Mensaje: {d['commit_message'] if d['commit_message'] else 'N/A'}

{sub}
REPOSITORIO
{sub}

Ruta: {d['repo_path']}

{sub}
ARCHIVOS MODIFICADOS
{sub}

{d['modified_files'] if d['modified_files'] else 'No hay información de archivos'}

{sub}
HISTORIAL DE REGISTRO
{sub}

Primera vez visto: {d['first_seen_date']}
Última actualización: {d['last_updated_date']}

{sep}
"""
    if d['branch_type'] == "reflog_recoverable":
        commands = "\n".join(recovery_commands(d['branch_name'], d['last_commit_hash']))
        text += f"""
COMANDOS PARA RECUPERAR LA RAMA
{sep}

{commands}

Nota: Revisa la rama antes de subirla al remoto.
"""
    return text
