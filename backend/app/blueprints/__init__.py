from .admin_users import bp as admin_users_bp
from .auth import bp as auth_bp
from .ruoyi_compat import bp as ruoyi_compat_bp
from .contests import bp as contests_bp
from .files import bp as files_bp, callback_bp as file_oauth_callback_bp
from .messages import bp as messages_bp
from .results import bp as results_bp
from .registrations import bp as registrations_bp
from .students import bp as students_bp
from .system_compat import bp as system_compat_bp
from .system import bp as system_bp


BLUEPRINTS = [
    ruoyi_compat_bp,
    admin_users_bp,
    auth_bp,
    system_bp,
    system_compat_bp,
    students_bp,
    contests_bp,
    files_bp,
    file_oauth_callback_bp,
    registrations_bp,
    messages_bp,
    results_bp,
]
