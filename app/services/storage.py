"""Extração e normalização de múltiplos discos, volumes e maior consumo por pasta/programa.

Por que este módulo existe:
  O pipeline original de gauges (`monitoring.gauge_metrics`) seleciona apenas um
  único item vencedor por categoria (`disk`), priorizando `C:` ou `/`, o que
  ocultava partições secundárias (`D:`, `E:`, `/dados`) e não expunha espaço
  livre/ocupado, tipo físico (HDD/SSD/NVMe) nem diretórios/programas mais pesados.

Para que serve:
  Consolidar, de forma somente leitura a partir dos itens retornados pela API
  Zabbix 7.0 (`item.get`), uma visão estruturada por host com:
  1. Todos os volumes/partições montadas (`vfs.fs.get`, `vfs.fs.dependent.size`,
     `vfs.fs.size`) com total, usado, livre e percentual.
  2. Discos físicos instalados (`smart.disk.get`, `wmi.getall` MSFT_PhysicalDisk /
     Win32_DiskDrive, `vfs.dev.discovery`) para distinguir HDD, SSD e NVMe.
  3. Pastas e programas que mais ocupam espaço em cada volume (via JSON de
     `UserParameter` `custom.disk.top_usage*` ou itens nativos `vfs.dir.size[*]`).
"""
import json
import math
import re
import time

# Sistemas de arquivos virtuais/pseudo que não representam discos de armazenamento
# reais quando retornados brutos pelo item mestre `vfs.fs.get`.
_IGNORED_FSTYPES = frozenset({
    "tmpfs", "devtmpfs", "sysfs", "proc", "devpts", "mqueue",
    "hugetlbfs", "securityfs", "debugfs", "tracefs", "squashfs",
    "iso9660", "overlay", "pstore", "bpf", "configfs", "fusectl",
    "efivarfs", "autofs", "rpc_pipefs", "binfmt_misc",
})

# Códigos numéricos de MSFT_PhysicalDisk (namespace root\microsoft\windows\storage).
_MSFT_MEDIA_TYPES = {
    "0": "Não especificado",
    "3": "HDD",
    "4": "SSD",
    "5": "SCM",
    3: "HDD",
    4: "SSD",
    5: "SCM",
}

_MSFT_BUS_TYPES = {
    1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre Channel",
    7: "USB", 8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD",
    13: "MMC", 14: "Virtual", 15: "File Backed Virtual", 16: "Storage Spaces",
    17: "NVMe",
}

_MSFT_HEALTH = {
    0: "Saudável", 1: "Atenção", 2: "Crítico", 5: "Desconhecido",
    "0": "Saudável", "1": "Atenção", "2": "Crítico", "5": "Desconhecido",
}

_FS_SIZE_RE = re.compile(
    r"^vfs\.fs\.(?:dependent\.)?size\[(.*),(total|used|free|pused|pfree)\]$",
    re.IGNORECASE,
)
_DIR_SIZE_RE = re.compile(r"^vfs\.dir\.size\[(.+)\]$", re.IGNORECASE)
_TOP_USAGE_KEY_RE = re.compile(
    r"^custom\.disk\.top_usage(?:\.get)?(?:\[(.*)\])?$",
    re.IGNORECASE,
)
_WINDOWS_DRIVE_RE = re.compile(r"^([a-z]):(?:\\|/|$)", re.IGNORECASE)


def _is_enabled_reading(item):
    """Confirma que o item está habilitado, suportado e possui timestamp válido."""
    if str(item.get("status", "0")) != "0":
        return False
    if str(item.get("state", "0")) not in ("0", ""):
        return False
    try:
        clock = int(item.get("lastclock") or 0)
    except (TypeError, ValueError):
        return False
    return clock > 0


def _parse_int_bytes(value):
    """Converte leitura em bytes garantindo inteiro não-negativo finito."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    # Proteção contra overflow uint64 reportado por alguns drivers virtuais Windows.
    if parsed >= 10 ** 18:
        return None
    return int(round(parsed))


def _parse_percent(value):
    """Valida leitura percentual no intervalo [0, 100]."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or not 0 <= parsed <= 100:
        return None
    return round(parsed, 2)


def _normalize_volume_name(raw):
    """Padroniza nome do volume (`"c:"` -> `"C:"`) para unificar chaves de LLD."""
    name = str(raw or "").strip().strip('"').strip("'")
    if re.fullmatch(r"[a-z]:[\\/]?", name, re.IGNORECASE):
        return name[:2].upper()
    if len(name) > 1 and name.endswith(("/", "\\")):
        name = name.rstrip("/\\")
    return name


def _split_first_arg(raw_args):
    """Extrai o primeiro argumento de chaves como `vfs.dir.size["C:\\Logs",...]`."""
    text = str(raw_args or "").strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end != -1:
            return text[1:end]
    return text.split(",", 1)[0].strip().strip('"')


def _volume_sort_key(entry):
    """Ordena volumes com `C:` e `/` primeiro, seguidos das demais letras/montagens."""
    vol = entry["volume"]
    if vol == "C:":
        return (0, "")
    if vol == "/":
        return (0, "/")
    if re.fullmatch(r"[A-Z]:", vol):
        return (1, vol)
    return (2, vol.lower())


def _new_volume(volume_name):
    return {
        "volume": volume_name,
        "label": None,
        "fstype": None,
        "drivetype": None,
        "total_bytes": None,
        "used_bytes": None,
        "free_bytes": None,
        "used_pct": None,
        "free_pct": None,
        "pused_itemid": None,
        "source": None,
        "lastclock": 0,
        "stale": False,
        "top_dirs": [],
        "top_apps": [],
        "top_updated": None,
    }


def _merge_vfs_fs_get(items, volumes, now):
    """Lê o item mestre JSON `vfs.fs.get` do Zabbix Agent/Agent 2.

    Por quê: em ambientes Windows/Linux com Agent 2, `vfs.fs.get` traz todos os
    volumes em uma única chamada (incluindo `fslabel`, `fstype` e `fsdrivetype`),
    mesmo antes ou independentemente de todos os protótipos LLD existirem.
    """
    for item in items:
        key = str(item.get("key_") or "").strip().lower()
        if key != "vfs.fs.get" or not _is_enabled_reading(item):
            continue
        clock = int(item.get("lastclock") or 0)
        try:
            payload = json.loads(item.get("lastvalue") or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, list):
            continue
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            fsname = _normalize_volume_name(entry.get("fsname"))
            if not fsname:
                continue
            fstype = str(entry.get("fstype") or "").strip()
            drivetype = str(entry.get("fsdrivetype") or "").strip().lower()
            if fstype.lower() in _IGNORED_FSTYPES or fstype.lower().startswith("cgroup"):
                continue
            bytes_obj = entry.get("bytes") if isinstance(entry.get("bytes"), dict) else {}
            total = _parse_int_bytes(bytes_obj.get("total"))
            free = _parse_int_bytes(bytes_obj.get("free"))
            used = _parse_int_bytes(bytes_obj.get("used"))
            pused = _parse_percent(bytes_obj.get("pused"))
            pfree = _parse_percent(bytes_obj.get("pfree"))

            # Ignora unidades ópticas sem mídia ou mounts virtuais de capacidade zero.
            if (drivetype == "cdrom" or total == 0) and not total:
                continue

            vol = volumes.setdefault(fsname, _new_volume(fsname))
            label = str(entry.get("fslabel") or "").strip()
            if label:
                vol["label"] = label
            if fstype:
                vol["fstype"] = fstype
            if drivetype:
                vol["drivetype"] = drivetype
            if total is not None and total > 0:
                vol["total_bytes"] = total
            if free is not None and (total is None or free <= total):
                vol["free_bytes"] = free
            if used is not None and (total is None or used <= total):
                vol["used_bytes"] = used
            if pused is not None:
                vol["used_pct"] = pused
            if pfree is not None:
                vol["free_pct"] = pfree
            vol["source"] = vol["source"] or "vfs.fs.get"
            vol["lastclock"] = max(vol["lastclock"], clock)
            vol["stale"] = (now - vol["lastclock"]) > 3600


def _merge_fs_size_items(items, volumes, now):
    """Consolida itens individuais/dependentes `vfs.fs.size` e `vfs.fs.dependent.size`."""
    for item in items:
        key = str(item.get("key_") or "").strip()
        match = _FS_SIZE_RE.match(key)
        if not match or not _is_enabled_reading(item):
            continue
        fsname = _normalize_volume_name(match.group(1))
        mode = match.group(2).lower()
        if not fsname:
            continue
        clock = int(item.get("lastclock") or 0)
        vol = volumes.setdefault(fsname, _new_volume(fsname))
        source = ("vfs.fs.dependent.size"
                  if key.lower().startswith("vfs.fs.dependent.size[")
                  else "vfs.fs.size")
        vol["source"] = source
        vol["lastclock"] = max(vol["lastclock"], clock)
        vol["stale"] = (now - vol["lastclock"]) > 3600

        if mode in ("total", "used", "free"):
            # Somente aceita leituras de capacidade em bytes (`B` ou vazio numérico válido).
            units = str(item.get("units") or "").strip()
            if units and units != "B":
                continue
            amount = _parse_int_bytes(item.get("lastvalue"))
            if amount is None:
                continue
            vol[f"{mode}_bytes"] = amount
        elif mode == "pused":
            pct = _parse_percent(item.get("lastvalue"))
            if pct is not None:
                vol["used_pct"] = pct
                vol["pused_itemid"] = str(item.get("itemid") or "")
        elif mode == "pfree":
            pct = _parse_percent(item.get("lastvalue"))
            if pct is not None:
                vol["free_pct"] = pct


def _finalize_volumes(volumes):
    """Preenche campos derivados consistentes (livre = total - usado) sem inventar dados."""
    finalized = []
    for vol in volumes.values():
        total = vol["total_bytes"]
        used = vol["used_bytes"]
        free = vol["free_bytes"]
        if total is not None and total > 0:
            if used is None and free is not None and free <= total:
                used = total - free
                vol["used_bytes"] = used
            if free is None and used is not None and used <= total:
                free = total - used
                vol["free_bytes"] = free
            if vol["used_pct"] is None and used is not None and used <= total:
                vol["used_pct"] = round(used * 100 / total, 2)
            if vol["free_pct"] is None and free is not None and free <= total:
                vol["free_pct"] = round(free * 100 / total, 2)
        if vol["used_pct"] is None and vol["free_pct"] is not None:
            vol["used_pct"] = round(100 - vol["free_pct"], 2)
        if vol["free_pct"] is None and vol["used_pct"] is not None:
            vol["free_pct"] = round(100 - vol["used_pct"], 2)

        # Só inclui volumes que possuem pelo menos capacidade ou percentual válido.
        if total is None and vol["used_pct"] is None and free is None and used is None:
            continue
        finalized.append(vol)
    finalized.sort(key=_volume_sort_key)
    return finalized


def _normalize_media_type(raw):
    text = str(raw or "").strip()
    if not text:
        return None
    upper = text.upper()
    if "NVME" in upper:
        return "NVMe"
    if "SSD" in upper or "SOLID STATE" in upper:
        return "SSD"
    if "HDD" in upper or "FIXED HARD DISK" in upper or "ROTATIONAL" in upper:
        return "HDD"
    return _MSFT_MEDIA_TYPES.get(text)


def _extract_physical_disks(items):
    """Identifica discos físicos instalados (HDD/SSD/NVMe) via SMART, WMI ou VFS dev."""
    disks = []
    seen = set()

    for item in items:
        if not _is_enabled_reading(item):
            continue
        key = str(item.get("key_") or "").strip()
        lower = key.lower()
        raw_value = str(item.get("lastvalue") or "").strip()
        if not raw_value:
            continue

        if lower == "smart.disk.get":
            try:
                parsed = json.loads(raw_value)
            except ValueError:
                continue
            entries = parsed if isinstance(parsed, list) else (
                list(parsed.values()) if isinstance(parsed, dict) else []
            )
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                disk_name = str(entry.get("disk_name") or entry.get("name") or "").strip()
                model = str(entry.get("model_name") or entry.get("model") or disk_name).strip()
                serial = str(entry.get("serial_number") or "").strip() or None
                dedup_key = ("smart", serial or disk_name or model)
                if dedup_key in seen or not (disk_name or model):
                    continue
                seen.add(dedup_key)
                raw_type = entry.get("disk_type") or (
                    "HDD" if (entry.get("rotation_rate") or 0) > 0 else ""
                )
                cap = entry.get("user_capacity")
                size_bytes = _parse_int_bytes(
                    cap.get("bytes") if isinstance(cap, dict) else entry.get("size")
                )
                temp = entry.get("temperature")
                temp_c = temp.get("current") if isinstance(temp, dict) else temp
                passed = entry.get("smart_status", {}).get("passed")
                health = ("Saudável" if passed is True
                          else ("Falha SMART" if passed is False else None))
                disks.append({
                    "id": disk_name or model,
                    "name": model or disk_name,
                    "model": model or None,
                    "media_type": _normalize_media_type(raw_type) or "Desconhecido",
                    "bus_type": str(entry.get("interface_type") or "").strip() or None,
                    "size_bytes": size_bytes,
                    "health": health,
                    "serial": serial,
                    "temperature_c": int(temp_c) if isinstance(temp_c, (int, float)) else None,
                    "source": "smart.disk.get",
                })

        elif lower.startswith("wmi.getall[") and (
            "msft_physicaldisk" in lower or "win32_diskdrive" in lower
        ):
            try:
                parsed = json.loads(raw_value)
            except ValueError:
                continue
            if not isinstance(parsed, list):
                continue
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                name = str(
                    entry.get("FriendlyName") or entry.get("Model")
                    or entry.get("Caption") or entry.get("DeviceID") or ""
                ).strip()
                if not name:
                    continue
                serial = str(entry.get("SerialNumber") or "").strip() or None
                dedup_key = ("wmi", serial or str(entry.get("DeviceID") or name))
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                media = _normalize_media_type(entry.get("MediaType"))
                bus_raw = entry.get("BusType")
                bus = (_MSFT_BUS_TYPES.get(bus_raw)
                       if isinstance(bus_raw, int)
                       else (str(entry.get("InterfaceType") or bus_raw or "").strip() or None))
                if media is None and bus == "NVMe":
                    media = "NVMe"
                disks.append({
                    "id": str(entry.get("DeviceID") or entry.get("ObjectId") or name),
                    "name": name,
                    "model": name,
                    "media_type": media or "Desconhecido",
                    "bus_type": bus,
                    "size_bytes": _parse_int_bytes(entry.get("Size")),
                    "health": _MSFT_HEALTH.get(entry.get("HealthStatus"),
                                                entry.get("Status")),
                    "serial": serial,
                    "temperature_c": None,
                    "source": "wmi.getall",
                })

        elif lower == "vfs.dev.discovery":
            try:
                parsed = json.loads(raw_value)
            except ValueError:
                continue
            if not isinstance(parsed, list):
                continue
            for entry in parsed:
                if not isinstance(entry, dict):
                    continue
                dev_name = str(entry.get("{#DEVNAME}") or entry.get("devname") or "").strip()
                dev_type = str(entry.get("{#DEVTYPE}") or entry.get("devtype") or "").strip()
                if not dev_name or (dev_type and dev_type != "disk"):
                    continue
                dedup_key = ("dev", dev_name)
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                disks.append({
                    "id": dev_name,
                    "name": dev_name,
                    "model": None,
                    "media_type": "NVMe" if "nvme" in dev_name.lower() else "Desconhecido",
                    "bus_type": "NVMe" if "nvme" in dev_name.lower() else None,
                    "size_bytes": None,
                    "health": None,
                    "serial": None,
                    "temperature_c": None,
                    "source": "vfs.dev.discovery",
                })

    return disks


def _normalize_top_entries(entries, *, is_app=False):
    """Normaliza lista de pastas/programas garantindo bytes inteiros e ordenação."""
    normalized = []
    if not isinstance(entries, list):
        return normalized
    for row in entries:
        if not isinstance(row, dict):
            continue
        size = _parse_int_bytes(row.get("bytes", row.get("size")))
        if size is None:
            continue
        path = str(row.get("path") or row.get("dir") or "").strip()
        name = str(row.get("name") or path).strip()
        if not name:
            continue
        item = {"name": name, "bytes": size}
        if path and (not is_app or path != name):
            item["path"] = path
        elif not is_app and path:
            item["path"] = path
        normalized.append(item)
    normalized.sort(key=lambda item: item["bytes"], reverse=True)
    return normalized[:20]


def _match_volume_for_path(path, volumes_by_name):
    """Associa um caminho (ex.: `C:\\Logs` ou `/var/log`) ao volume mais específico."""
    if not path or not volumes_by_name:
        return None
    win = _WINDOWS_DRIVE_RE.match(path.strip())
    if win:
        drive = win.group(1).upper() + ":"
        return drive if drive in volumes_by_name else None
    clean = path.strip()
    candidates = [
        vol_name for vol_name in volumes_by_name
        if vol_name.startswith("/") and (
            clean == vol_name
            or vol_name == "/"
            or clean.startswith(vol_name.rstrip("/") + "/")
        )
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _merge_top_usage(items, volumes_by_name):
    """Anexa pastas e programas mais pesados a cada volume.

    Aceita duas origens semânticas:
    1. Itens customizados em JSON (`custom.disk.top_usage` ou `custom.disk.top_usage[C:]`),
       produzidos por `UserParameter` no Agent 2 com `top_dirs` e `top_apps`.
    2. Itens nativos `vfs.dir.size[caminho,...]`, agregados por ponto de montagem.
    """
    for item in items:
        if not _is_enabled_reading(item):
            continue
        key = str(item.get("key_") or "").strip()
        clock = int(item.get("lastclock") or 0)

        top_match = _TOP_USAGE_KEY_RE.match(key)
        if top_match:
            try:
                payload = json.loads(item.get("lastvalue") or "null")
            except (TypeError, ValueError):
                continue
            target_arg = _normalize_volume_name(top_match.group(1) or "")
            if isinstance(payload, dict) and ("top_dirs" in payload or "top_apps" in payload):
                vol_name = _normalize_volume_name(payload.get("drive") or target_arg)
                vol = volumes_by_name.get(vol_name)
                if vol:
                    vol["top_dirs"] = _normalize_top_entries(payload.get("top_dirs"))
                    vol["top_apps"] = _normalize_top_entries(payload.get("top_apps"), is_app=True)
                    vol["top_updated"] = max(vol["top_updated"] or 0, clock)
            elif isinstance(payload, dict):
                for drive_key, entry in payload.items():
                    if not isinstance(entry, dict):
                        continue
                    vol_name = _normalize_volume_name(drive_key)
                    vol = volumes_by_name.get(vol_name)
                    if not vol:
                        continue
                    vol["top_dirs"] = _normalize_top_entries(entry.get("top_dirs"))
                    vol["top_apps"] = _normalize_top_entries(entry.get("top_apps"), is_app=True)
                    vol["top_updated"] = max(vol["top_updated"] or 0, clock)
            elif isinstance(payload, list):
                for entry in payload:
                    if not isinstance(entry, dict):
                        continue
                    vol_name = _normalize_volume_name(
                        entry.get("drive") or entry.get("volume") or target_arg
                    )
                    vol = volumes_by_name.get(vol_name)
                    if not vol:
                        continue
                    vol["top_dirs"] = _normalize_top_entries(entry.get("top_dirs"))
                    vol["top_apps"] = _normalize_top_entries(entry.get("top_apps"), is_app=True)
                    vol["top_updated"] = max(vol["top_updated"] or 0, clock)
            continue

        dir_match = _DIR_SIZE_RE.match(key)
        if dir_match:
            dir_path = _split_first_arg(dir_match.group(1))
            size_bytes = _parse_int_bytes(item.get("lastvalue"))
            vol_name = _match_volume_for_path(dir_path, volumes_by_name)
            if dir_path and size_bytes is not None and vol_name:
                vol = volumes_by_name[vol_name]
                existing = {row.get("path"): row for row in vol["top_dirs"] if row.get("path")}
                if dir_path not in existing:
                    vol["top_dirs"].append({
                        "name": dir_path, "path": dir_path, "bytes": size_bytes,
                    })
                    vol["top_dirs"].sort(key=lambda row: row["bytes"], reverse=True)
                    vol["top_dirs"] = vol["top_dirs"][:20]
                    vol["top_updated"] = max(vol["top_updated"] or 0, clock)


def extract_storage(items, now=None):
    """Constrói inventário completo de volumes, discos físicos e consumo por pasta/app."""
    now = int(time.time()) if now is None else int(now)
    volumes = {}
    _merge_vfs_fs_get(items or [], volumes, now)
    _merge_fs_size_items(items or [], volumes, now)
    finalized_volumes = _finalize_volumes(volumes)
    volumes_by_name = {vol["volume"]: vol for vol in finalized_volumes}
    _merge_top_usage(items or [], volumes_by_name)
    physical_disks = _extract_physical_disks(items or [])

    known_totals = [
        vol["total_bytes"] for vol in finalized_volumes if vol["total_bytes"] is not None
    ]
    known_used = [vol["used_bytes"] for vol in finalized_volumes if vol["used_bytes"] is not None]
    known_free = [vol["free_bytes"] for vol in finalized_volumes if vol["free_bytes"] is not None]
    sum_total = sum(known_totals) if known_totals else None
    sum_used = sum(known_used) if known_used else None
    sum_free = sum(known_free) if known_free else None
    sum_pct = (round(sum_used * 100 / sum_total, 2)
               if sum_total and sum_used is not None else None)

    return {
        "volumes": finalized_volumes,
        "physical_disks": physical_disks,
        "totals": {
            "volume_count": len(finalized_volumes),
            "physical_count": len(physical_disks),
            "total_bytes": sum_total,
            "used_bytes": sum_used,
            "free_bytes": sum_free,
            "used_pct": sum_pct,
        },
    }
