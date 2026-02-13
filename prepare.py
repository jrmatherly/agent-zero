import os
import random
import string

from python.helpers import dotenv, runtime, settings
from python.helpers.print_style import PrintStyle

PrintStyle.phase("⚙️", "Preparing environment")

try:
    runtime.initialize()

    # Root password setup requires root privileges (chpasswd).
    # When running as non-root (e.g. appuser via supervisord), skip —
    # initialize.sh handles this before supervisord starts.
    if os.getuid() == 0:
        root_pass = dotenv.get_dotenv_value(dotenv.KEY_ROOT_PASSWORD)
        if not root_pass:
            root_pass = "".join(
                random.choices(string.ascii_letters + string.digits, k=32)
            )
        settings.set_root_password(root_pass)
        PrintStyle.step("Root password", "configured")
    else:
        PrintStyle.step("Root password", "skipped (not root)")

except Exception as e:
    PrintStyle.error(f"Error in preload: {e}")
