"""Git Branch Info & Recovery: metadatos del proyecto."""

__proyect__    = 'Git Branch Info & Recovery (with SQLite History)'
__author__     = "Mario Rubio"
__copyright__  = "Copyright 2022, The MRubioDev Project"
__credits__    = ["Mario Rubio"]
__license__    = "GPL"
__version__    = "V26.09.028"
__maintainer__ = "Mario Rubio"
__email__      = "https://mrubiodev.com/"
__status__     = "Development" #"Prototype", "Development", or "Production"

# Default database path. Use a user-local data directory to avoid
# attempt-to-write readonly-database errors when the app is installed
# into a system location (e.g., Program Files) or run from a read-only
# folder. The path can still be overridden with `--db` on the CLI.
import os

DEFAULT_DB_PATH = os.path.join(os.path.expanduser("~"), ".git_branch_info", "git_branches.db")
