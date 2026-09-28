"""Helpers para extraer datos de commits de GitPython."""
import datetime

MAX_FILES_SHOWN = 10


def format_timestamp(ts):
    return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else ""


def commit_summary(commit):
    """(primera línea del mensaje, fecha formateada, nombre del autor)."""
    return (commit.message.strip().split('\n')[0],
            format_timestamp(commit.committed_date),
            commit.author.name)


def modified_files(commit):
    """Ficheros modificados en el commit respecto a su primer padre."""
    if commit.parents:
        diffs = commit.parents[0].diff(commit)
        return [d.a_path if d.a_path else d.b_path for d in diffs]
    # Primer commit: todos los ficheros son nuevos
    return [item.path for item in commit.tree.traverse() if item.type == 'blob']


def summarize_files(files, limit=MAX_FILES_SHOWN):
    text = ", ".join(files[:limit])
    if len(files) > limit:
        text += f" ... (+{len(files) - limit} más)"
    return text
