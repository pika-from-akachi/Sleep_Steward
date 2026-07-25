#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)}"
service_name="baby-good-sleep-hardware.service"
install_dir="/opt/baby-good-sleep"
binary_tmp="$(mktemp /tmp/dht11-read.XXXXXX)"

cleanup() {
  rm -f "$binary_tmp"
}
trap cleanup EXIT

if [[ "$(id -u)" -ne 0 ]]; then
  echo "install.sh must run as root" >&2
  exit 1
fi

for command_name in gcc python3 systemctl install; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "missing required command: $command_name" >&2
    exit 1
  fi
done

for required_file in hardware_agent.py dht11_read.c "$service_name"; do
  if [[ ! -f "$source_dir/$required_file" ]]; then
    echo "missing deployment file: $source_dir/$required_file" >&2
    exit 1
  fi
done

if ! python3 -c 'import Hobot.GPIO' >/dev/null 2>&1; then
  echo "Python module Hobot.GPIO is unavailable" >&2
  exit 1
fi

gcc -O2 "$source_dir/dht11_read.c" -lgpiod -o "$binary_tmp"

systemctl stop "$service_name" >/dev/null 2>&1 || true
install -d -m 0755 "$install_dir"
install -m 0755 "$binary_tmp" /usr/local/bin/dht11-read
install -m 0755 "$source_dir/hardware_agent.py" "$install_dir/hardware_agent.py"
install -m 0644 "$source_dir/$service_name" "/etc/systemd/system/$service_name"

systemctl daemon-reload
systemctl enable --now "$service_name"

if ! systemctl is-active --quiet "$service_name"; then
  systemctl status "$service_name" --no-pager >&2 || true
  exit 1
fi

echo "installed $service_name"
echo "health endpoint: http://127.0.0.1:8765/health"
