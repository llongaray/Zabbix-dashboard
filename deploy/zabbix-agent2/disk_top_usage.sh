#!/usr/bin/env bash
# Coleta as pastas e pacotes que mais ocupam espaço em cada ponto de montagem Linux.
#
# Por quê: o Zabbix Agent 2 não entrega ranking automático de pastas/programas por volume.
# Para quê: executado via `UserParameter=custom.disk.top_usage` a cada 30-60 min,
# gerando JSON consumido pelo Zabbix Dashboard no detalhamento da VM.
set -euo pipefail

TOP_COUNT="${1:-10}"

python3 - "$TOP_COUNT" <<'PY'
import json
import os
import subprocess
import sys

top_count = int(sys.argv[1])
IGNORED_FS = {
    "tmpfs", "devtmpfs", "sysfs", "proc", "devpts", "cgroup", "cgroup2",
    "overlay", "squashfs", "iso9660", "mqueue", "hugetlbfs", "debugfs",
    "tracefs", "securityfs", "pstore", "bpf", "configfs", "efivarfs",
}

mounts = []
with open("/proc/mounts", encoding="utf-8") as fh:
    for line in fh:
        parts = line.split()
        if len(parts) < 3:
            continue
        device, target, fstype = parts[0], parts[1], parts[2]
        if fstype in IGNORED_FS or not device.startswith("/"):
            continue
        mounts.append(target)

mounts = sorted(set(mounts), key=lambda p: (0 if p == "/" else 1, len(p), p))

def top_dirs_for(mount):
    try:
        proc = subprocess.run(
            ["du", "-x", "-B1", "--max-depth=2", mount],
            capture_output=True, text=True, timeout=25, check=False,
        )
    except Exception:
        return []
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        try:
            size = int(parts[0])
        except ValueError:
            continue
        path = parts[1].strip()
        if path == mount:
            continue
        rows.append({"path": path, "bytes": size})
    rows.sort(key=lambda r: r["bytes"], reverse=True)
    return rows[:top_count]

def top_packages():
    for cmd, factor in (
        (["dpkg-query", "-W", "-f=${Package}\t${Installed-Size}\n"], 1024),
        (["rpm", "-qa", "--qf", "%{NAME}\t%{SIZE}\n"], 1),
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            if proc.returncode != 0 or not proc.stdout:
                continue
            pkgs = []
            for line in proc.stdout.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                try:
                    pkgs.append({"name": parts[0].strip(), "bytes": int(parts[1]) * factor})
                except ValueError:
                    continue
            pkgs.sort(key=lambda r: r["bytes"], reverse=True)
            return pkgs[:top_count]
        except FileNotFoundError:
            continue
    return []

root_apps = top_packages()
output = {}
for mount in mounts:
    output[mount] = {
        "top_dirs": top_dirs_for(mount),
        "top_apps": root_apps if mount == "/" else [],
    }

print(json.dumps(output, separators=(",", ":")))
PY
