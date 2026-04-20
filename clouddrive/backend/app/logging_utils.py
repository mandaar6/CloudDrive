import json
import logging
from datetime import datetime

logger = logging.getLogger("clouddrive")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    logger.addHandler(handler)

def log_event(event, level="info", **kwargs):
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "service": "backend",
        "event": event,
        "level": level,
        **kwargs
    }
    line = json.dumps(payload)

    if level == "error":
        logger.error(line)
    elif level == "warning":
        logger.warning(line)
    else:
        logger.info(line)

# created after perplexity usage