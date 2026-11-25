#!/usr/bin/env bash
# Run once in Oracle Cloud Shell. Creates an API key for GitHub, uploads it to your Oracle user,
# and prints ONE value to paste into GitHub secret OCI_CONFIG. GitHub then keeps retrying the free server.
set -euo pipefail
C="${OCI_TENANCY:?}"; REG="${OCI_REGION:-ap-mumbai-1}"
USER_ID=$(oci iam user list -c "$C" --query "data[?contains(name,'genzpulsehub')].id | [0]" --raw-output)
mkdir -p ~/.gph && cd ~/.gph
[ -f api.pem ] || { openssl genrsa -out api.pem 2048 2>/dev/null; openssl rsa -pubout -in api.pem -out api_pub.pem 2>/dev/null; }
FP=$(openssl rsa -pubout -outform DER -in api.pem 2>/dev/null | python3 -c "import sys,hashlib;h=hashlib.md5(sys.stdin.buffer.read(),usedforsecurity=False).hexdigest();print(':'.join(h[i:i+2] for i in range(0,32,2)))")
oci iam user api-key list --user-id "$USER_ID" --query 'data[].fingerprint' --raw-output | grep -q "$FP" || \
  oci iam user api-key upload --user-id "$USER_ID" --key-file api_pub.pem >/dev/null
# remove any older GitHub keys (e.g. after a rotation), keep only the current one
for old in $(oci iam user api-key list --user-id "$USER_ID" --query 'data[].fingerprint' --raw-output | tr -d '[]",' ); do
  [ "$old" != "$FP" ] && oci iam user api-key delete --user-id "$USER_ID" --fingerprint "$old" --force >/dev/null && echo "removed old key $old"
done
[ -f ~/.ssh/gph ] || ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/gph -q
python3 - "$USER_ID" "$C" "$FP" "$REG" <<'P'
import sys, json, base64, os
u, t, fp, r = sys.argv[1:5]
d = {"user": u, "tenancy": t, "fingerprint": fp, "region": r,
     "key": open(os.path.expanduser("~/.gph/api.pem")).read(),
     "ssh_pub": open(os.path.expanduser("~/.ssh/gph.pub")).read().strip()}
print("\n===== COPY EVERYTHING BETWEEN THE LINES (one long line) =====")
print(base64.b64encode(json.dumps(d).encode()).decode())
print("===== END =====\n")
P
