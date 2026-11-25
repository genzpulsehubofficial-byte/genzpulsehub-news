#!/usr/bin/env bash
# Run inside Oracle Cloud Shell:  curl -fsSL https://raw.githubusercontent.com/genzpulsehubofficial-byte/genzpulsehub-news/main/stream/oci_create.sh | bash
# Creates network + Always Free ARM VM (4 OCPU / 24 GB) that boots straight into the GenZ Pulse Hub stream box.
set -euo pipefail
C="${OCI_TENANCY:?no tenancy}"; NAME=gph-stream
q(){ oci "$@" --query 'data.id' --raw-output; }
say(){ echo -e "\n>>> $*"; }

[ -f ~/.ssh/gph ] || ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/gph -q
VCN=$(oci network vcn list -c "$C" --display-name gph-vcn --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -z "$VCN" ] || [ "$VCN" = "None" ]; then
  say "Creating network"
  VCN=$(q network vcn create -c "$C" --cidr-block 10.0.0.0/16 --display-name gph-vcn --dns-label gph --wait-for-state AVAILABLE)
  IGW=$(q network internet-gateway create -c "$C" --vcn-id "$VCN" --is-enabled true --display-name gph-igw --wait-for-state AVAILABLE)
  RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
  oci network route-table update --rt-id "$RT" --force --route-rules "[{\"destination\":\"0.0.0.0/0\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
  q network subnet create -c "$C" --vcn-id "$VCN" --cidr-block 10.0.1.0/24 --display-name gph-subnet --dns-label pub --wait-for-state AVAILABLE >/dev/null
fi
SUB=$(oci network subnet list -c "$C" --vcn-id "$VCN" --query 'data[0].id' --raw-output)
IMG=$(oci compute image list -c "$C" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" \
      --shape VM.Standard.A1.Flex --sort-by TIMECREATED --query 'data[0].id' --raw-output)
curl -fsSL https://raw.githubusercontent.com/genzpulsehubofficial-byte/genzpulsehub-news/main/stream/cloud-init.sh -o /tmp/ci.sh

EXIST=$(oci compute instance list -c "$C" --display-name $NAME --lifecycle-state RUNNING --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -n "$EXIST" ] && [ "$EXIST" != "None" ]; then ID=$EXIST; say "Server already exists"
else
  say "Creating Always Free server (retries if Oracle is out of capacity)"
  for try in $(seq 1 60); do
    for AD in $(oci iam availability-domain list -c "$C" --query 'data[].name' --raw-output | tr -d '[]",'); do
      if ID=$(q compute instance launch -c "$C" --availability-domain "$AD" --display-name $NAME \
          --shape VM.Standard.A1.Flex --shape-config '{"ocpus":4,"memoryInGBs":24}' \
          --image-id "$IMG" --subnet-id "$SUB" --assign-public-ip true --boot-volume-size-in-gbs 100 \
          --ssh-authorized-keys-file ~/.ssh/gph.pub --user-data-file /tmp/ci.sh --wait-for-state RUNNING 2>/tmp/err); then
        break 2
      fi
      grep -qi "capacity" /tmp/err && echo "  out of capacity in $AD, try $try/60" || { cat /tmp/err; exit 1; }
    done
    sleep 60
  done
fi
IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output)
echo "$IP" > ~/.gph_ip
say "DONE. Server IP: $IP  (it installs itself over ~10 minutes)"
