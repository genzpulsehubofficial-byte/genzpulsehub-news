#!/usr/bin/env bash
# Run in Oracle Cloud Shell. Asks for the 4 stream keys (paste each, press Enter; blank = skip) and installs them on the server.
set -euo pipefail
ID=$(oci compute instance list -c "$OCI_TENANCY" --display-name gph-stream --lifecycle-state RUNNING --query "data[0].id" --raw-output); IP=$(oci compute instance list-vnics --instance-id "$ID" --query "data[0].\"public-ip\"" --raw-output); echo "Server: $IP"
ask(){ local v; read -rsp "Paste $1 then Enter (or just Enter to skip): " v </dev/tty; echo; [ -n "$v" ] && echo "$2=$v" >> /tmp/gph.env || true; }
: > /tmp/gph.env; chmod 600 /tmp/gph.env
ask "YouTube ENGLISH stream key" YT_KEY_EN
ask "YouTube MALAYALAM stream key" YT_KEY_ML
ask "Facebook ENGLISH stream key" FB_KEY_EN
ask "Facebook MALAYALAM stream key" FB_KEY_ML
ask "Discord webhook URL (for stream alerts)" DISCORD_WEBHOOK_URL
SSH="ssh -i $HOME/.ssh/gph -o StrictHostKeyChecking=accept-new ubuntu@$IP"
# merge: keep existing keys that weren't re-entered
$SSH "sudo cat /etc/gph.env 2>/dev/null" > /tmp/old.env || true
cut -d= -f1 /tmp/gph.env | while read k; do sed -i "/^$k=/d" /tmp/old.env; done
cat /tmp/old.env /tmp/gph.env | grep -v '^$' > /tmp/new.env
scp -i ~/.ssh/gph -q /tmp/new.env ubuntu@$IP:/tmp/gph.env
$SSH "sudo install -m600 /tmp/gph.env /etc/gph.env && rm /tmp/gph.env && sudo systemctl restart gph-stream@en gph-stream@ml"
rm -f /tmp/gph.env /tmp/old.env /tmp/new.env
echo "Saved: $(cut -d= -f1 <<<"$($SSH 'sudo cat /etc/gph.env')" | tr '\n' ' ')"
echo "Streams restarted. They go live within ~1 minute."
