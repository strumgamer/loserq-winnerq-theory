#!/usr/bin/env bash
# Renouvelle la clé Riot API dans ~/.riot_secrets sans qu'elle passe dans l'historique shell.
# À relancer chaque jour (clé de dev expire toutes les 24h).
# Usage : bash renew_key.sh

set -euo pipefail

SECRETS_FILE="$HOME/.riot_secrets"

read -rs -p "Nouvelle clé Riot (RGAPI-...) : " key && echo

if [[ ! "$key" =~ ^RGAPI-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo "Format invalide. Attendu : RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" >&2
    exit 1
fi

echo "export RIOT_API_KEY=\"$key\"" > "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"
unset key

echo "Clé enregistrée dans $SECRETS_FILE"
echo "Recharge le terminal ou lance : source $SECRETS_FILE"
