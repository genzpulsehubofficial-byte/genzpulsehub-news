#!/bin/bash
# Runs once on first boot of the Oracle VM. Installs everything and keeps the code auto-updated from GitHub.
set -x
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ffmpeg git python3-pip python3-venv fonts-noto-core fonts-noto-ui-core libraqm0 curl
git clone https://github.com/genzpulsehubofficial-byte/genzpulsehub-news /opt/gph || (cd /opt/gph && git pull)
python3 -m venv /opt/venv && /opt/venv/bin/pip install -q -U edge-tts gTTS requests pillow
touch /etc/gph.env && chmod 600 /etc/gph.env
cat >/etc/systemd/system/gph-update.service <<'U'
[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cd /opt/gph && old=$(git rev-parse HEAD) && git pull -q && [ "$old" != "$(git rev-parse HEAD)" ] && systemctl restart gph-stream@en gph-stream@ml || true'
U
cat >/etc/systemd/system/gph-update.timer <<'U'
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
U
cat >/etc/systemd/system/gph-stream@.service <<'U'
[Unit]
After=network-online.target
[Service]
EnvironmentFile=/etc/gph.env
ExecStart=/bin/bash /opt/gph/stream/run.sh %i
Restart=always
RestartSec=20
[Install]
WantedBy=multi-user.target
U
systemctl daemon-reload
systemctl enable --now gph-update.timer gph-stream@en gph-stream@ml
