#!/usr/bin/env bash
# Run in Oracle Cloud Shell: shows server health and stream logs.
IP=$(cat ~/.gph_ip); SSH="ssh -i $HOME/.ssh/gph -o StrictHostKeyChecking=accept-new ubuntu@$IP"
$SSH 'cloud-init status; uptime; for l in en ml; do echo "== $l"; sudo journalctl -u gph-stream@$l -n 8 --no-pager; done'
