#!/usr/bin/env bash
# Run in Oracle Cloud Shell: shows server health and stream logs.
ID=$(oci compute instance list -c "$OCI_TENANCY" --display-name gph-stream --lifecycle-state RUNNING --query "data[0].id" --raw-output); IP=$(oci compute instance list-vnics --instance-id "$ID" --query "data[0].\"public-ip\"" --raw-output); echo "Server: $IP"; SSH="ssh -i $HOME/.ssh/gph -o StrictHostKeyChecking=accept-new ubuntu@$IP"
$SSH 'cloud-init status; uptime; for l in en ml; do echo "== $l"; sudo journalctl -u gph-stream@$l -n 8 --no-pager; done'
