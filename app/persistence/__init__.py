"""Domain persistence. `app.db` remains the compatibility facade used by repositories.

New data-access code should live beside the matching domain module rather than growing
`app/db.py` further.
"""

from app.db import (
    cleanup_expired,
    list_runs,
    load_run,
    save_run,
    verify_audit_chain,
)
