#!/bin/bash
set -e

# cron ne connaît pas les variables d'environnement passées au conteneur
# (BDD_URL, LITELLM_PROXY_URL, etc.) : on les écrit dans /etc/environment
# pour qu'elles soient chargées avant chaque exécution de job.
printenv | grep -v "no_proxy" | sed 's/^\(.*\)$/\1/g' > /etc/environment

echo "[entrypoint] Démarrage de cron (TZ=$(cat /etc/timezone))"
cron

# Garde le conteneur au premier plan et fait remonter les logs des jobs
# dans 'docker logs'
tail -f /var/log/cron.log