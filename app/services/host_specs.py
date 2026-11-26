"""Especificações provenientes dos itens e do inventário do Zabbix."""
import json
import re

from app.services import storage


def overview_summary(record, now):
    items = record.get("items", [])
    gauges = record["gauges"]
    disk = gauges.get("disk", {})
    disk_item = next((item for item in items if item.get("itemid") == disk.get("itemid")
                      and disk.get("itemid")), None)
    total = volume = None
    if disk_item:
        volume_key = disk_item["key_"].rsplit(",", 1)[0]
        volume = volume_key.partition("[")[2].strip('"')
        total_item = next((item for item in items
                           if item["key_"] == volume_key + ",total]"), None)
        if total_item and total_item.get("units") == "B":
            reading = str(total_item.get("lastvalue", ""))
            clock = str(total_item.get("lastclock", ""))
            if reading.isdecimal() and int(reading) > 0 and clock.isdecimal() and int(clock) > 0:
                total = int(reading)

    # Consolida todos os volumes descobertos para exibir soma total no card de resumo
    # sem perder a referência individual (`disk_bytes` / `disk_volume`) do volume raiz.
    storage_info = record.get("storage") or storage.extract_storage(items, now=now)
    totals = storage_info.get("totals") or {}
    volumes = storage_info.get("volumes") or []
    if total is None and volumes:
        primary = volumes[0]
        total = primary.get("total_bytes")
        volume = primary.get("volume")

    status = "stale"
    if any(now - metric.get("lastclock", 0) <= 3600 for metric in gauges.values()):
        status = "recent"
    for item in items:
        if item["key_"] != "icmpping":
            continue
        clock = str(item.get("lastclock", ""))
        value = str(item.get("lastvalue", ""))
        if clock.isdecimal() and 0 <= now - int(clock) <= 300 and value in ("0", "1"):
            status = "online" if value == "1" else "unreachable"
        break
    return {
        "specs": record.get("specs") or specifications(items, None),
        "disk_bytes": total,
        "disk_volume": volume,
        "disks_count": totals.get("volume_count", len(volumes)),
        "disks_total_bytes": totals.get("total_bytes"),
        "disks_used_bytes": totals.get("used_bytes"),
        "disks_free_bytes": totals.get("free_bytes"),
        "status": status,
    }


def specifications(items, inventory):
    readings = {}
    for item in items:
        if str(item.get("status", "0")) != "0":
            continue
        clock = str(item.get("lastclock", "0"))
        value = str(item.get("lastvalue") or "").strip()
        if value and clock.isdecimal() and int(clock) > 0:
            readings[item["key_"].lower()] = value

    inventory = inventory if isinstance(inventory, dict) else {}
    os_name = (readings.get("system.sw.os[name]") or readings.get("system.sw.os")
               or readings.get("system.sw.os[full]") or readings.get("system.sw.os[short]")
               or inventory.get("os_full") or inventory.get("os") or inventory.get("os_short")
               or readings.get("system.uname"))
    try:
        os_details = json.loads(readings.get("system.sw.os.get", "{}"))
    except ValueError:
        os_details = {}
    if isinstance(os_details, dict):
        name = os_details.get("pretty_name")
        if isinstance(name, str) and name.strip():
            os_name = name.strip()

    family = None
    if os_name:
        if re.search(r"\bwindows\b", os_name, re.I):
            family = "windows"
            os_name = re.sub(r"\s+\d+\.\d+\.[^\s]+.*?(?=\s+Build\s+\d|$)", "", os_name)
        elif re.search(r"\b(linux|ubuntu|debian|fedora|centos|rocky|almalinux|red hat|suse)\b",
                       os_name, re.I):
            family = "linux"
            kernel = re.match(r"Linux version (\S+)", os_name, re.I)
            if kernel:
                os_name = "Linux · Kernel " + kernel[1]

    model = readings.get("system.hw.cpu[0,model]") or readings.get("system.hw.cpu[all,model]")
    if not model:
        model = next((
            value for key, value in readings.items()
            if re.fullmatch(
                r'wmi\.get\[root[\\/]cimv2,\s*"?select\s+name\s+from\s+win32_processor"?\]',
                key,
            )
        ), None)
    cores = readings.get("system.cpu.num[online]") or readings.get("system.cpu.num")
    if not cores:
        cores = next((value for key, value in readings.items() if re.fullmatch(
            r'wmi\.get\[root[\\/]cimv2,\s*"?select\s+numberoflogicalprocessors\s+'
            r'from\s+win32_computersystem"?\]', key,
        )), None)
    ram = readings.get("vm.memory.size[total]")
    return {
        "os": os_name, "os_family": family,
        "architecture": readings.get("system.sw.arch"),
        "cpu_model": model,
        "logical_cpus": int(cores) if cores and cores.isdecimal() and int(cores) > 0 else None,
        "ram_bytes": int(ram) if ram and ram.isdecimal() and int(ram) > 0 else None,
    }
