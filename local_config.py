"""Load optional external JSON secrets before Flask is initialized."""
import json
import os
from pathlib import Path

CONFIG_KEYS = {
    'SECRET_KEY', 'VAPID_PUBLIC_KEY', 'VAPID_PRIVATE_KEY', 'VAPID_SUBJECT',
    'MIKROTIK_API_TOKEN', 'PUBLIC_BASE_URL',
    'PORT', 'PPPOE_ROOT', 'LIVE_SAMPLE_MAX_GAP_SECONDS',
}


def load_config():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name('.env'), override=False)
    pointer = Path(__file__).with_name('.local-config-path')
    location = os.environ.get('JSS_CONFIG_FILE')
    if not location and pointer.exists():
        location = pointer.read_text(encoding='utf-8').strip()
    if not location:
        return
    values = json.loads(Path(location).read_text(encoding='utf-8'))
    for key in CONFIG_KEYS:
        if key in values:
            current = os.environ.get(key)
            if not current or (key == 'SECRET_KEY' and current == 'ganti-dengan-random-secret'):
                os.environ[key] = str(values[key])
