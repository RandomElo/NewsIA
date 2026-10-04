import logging

# Un seul format pour tous les scripts lancés par cron : "[04/10 09:01:54] message".
# Les bibliothèques (playwright, urllib3, newspaper...) restent au niveau WARNING
# pour ne pas noyer docker logs.
logging.basicConfig(
    level=logging.WARNING,
    format="[%(asctime)s] %(message)s",
    datefmt="%d/%m %H:%M:%S",
)

log = logging.getLogger("newsia")
log.setLevel(logging.INFO)
