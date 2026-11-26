"""Testes de extração multi-disco, HDD/SSD/NVMe, top pastas/apps e API Zabbix 7.0."""
import json
import time

from app.services import host_specs, storage, zabbix


def make_item(key, value, units="", value_type="0", name="Item", itemid="1", **extra):
    return {
        "itemid": itemid,
        "key_": key,
        "name": name,
        "lastvalue": value,
        "units": units,
        "value_type": value_type,
        "status": "0",
        "state": "0",
        "lastclock": str(extra.pop("lastclock", int(time.time()))),
        **extra,
    }


def test_extracts_all_volumes_from_vfs_fs_get_and_dependent_items():
    fs_get = json.dumps([
        {
            "fsname": "C:",
            "fstype": "NTFS",
            "fslabel": "Sistema",
            "fsdrivetype": "fixed",
            "bytes": {
                "total": 100 * 1024 ** 3,
                "free": 40 * 1024 ** 3,
                "used": 60 * 1024 ** 3,
                "pfree": 40.0,
                "pused": 60.0,
            },
        },
        {
            "fsname": "D:",
            "fstype": "NTFS",
            "fslabel": "Dados",
            "fsdrivetype": "fixed",
            "bytes": {
                "total": 500 * 1024 ** 3,
                "free": 100 * 1024 ** 3,
                # Simula bug de overflow uint64 do Windows em bytes.used
                "used": 18446743833951000000,
                "pfree": 20.0,
                "pused": 80.0,
            },
        },
        {
            "fsname": "E:",
            "fstype": "CDFS",
            "fslabel": "",
            "fsdrivetype": "cdrom",
            "bytes": {"total": 0, "free": 0, "used": 0, "pfree": 0, "pused": 0},
        },
    ])
    items = [
        make_item("vfs.fs.get", fs_get, value_type="4", itemid="10"),
        make_item('vfs.fs.dependent.size["C:",pused]', "61.5", "%", itemid="11"),
        make_item('vfs.fs.dependent.size["D:",pused]', "80.0", "%", itemid="12"),
        make_item('vfs.fs.size["F:",total]', str(200 * 1024 ** 3), "B",
                  value_type="3", itemid="13"),
        make_item('vfs.fs.size["F:",free]', str(150 * 1024 ** 3), "B", value_type="3", itemid="14"),
    ]

    result = storage.extract_storage(items)
    volumes = {v["volume"]: v for v in result["volumes"]}

    assert set(volumes) == {"C:", "D:", "F:"}
    assert volumes["C:"]["label"] == "Sistema"
    assert volumes["C:"]["used_pct"] == 61.5
    assert volumes["C:"]["pused_itemid"] == "11"
    # Overflow descartado e recalculado a partir de total - free
    assert volumes["D:"]["used_bytes"] == 400 * 1024 ** 3
    assert volumes["D:"]["free_bytes"] == 100 * 1024 ** 3
    assert volumes["F:"]["used_bytes"] == 50 * 1024 ** 3
    assert volumes["F:"]["used_pct"] == 25.0
    assert result["totals"]["volume_count"] == 3
    assert result["totals"]["total_bytes"] == 800 * 1024 ** 3


def test_extracts_physical_disks_hdd_ssd_nvme():
    smart_json = json.dumps([
        {
            "disk_name": "/dev/nvme0n1",
            "model_name": "Samsung SSD 980 PRO 1TB",
            "disk_type": "nvme",
            "serial_number": "S123",
            "user_capacity": {"bytes": 1000204886016},
            "smart_status": {"passed": True},
            "temperature": {"current": 37},
        }
    ])
    wmi_json = json.dumps([
        {
            "FriendlyName": "WDC WD2003FZEX",
            "MediaType": 3,
            "BusType": 11,
            "Size": 2000398934016,
            "HealthStatus": 0,
            "SerialNumber": "WD-999",
        },
        {
            "FriendlyName": "Crucial MX500",
            "MediaType": 4,
            "BusType": 11,
            "Size": 500107862016,
            "HealthStatus": 0,
            "SerialNumber": "CR-888",
        },
    ])
    items = [
        make_item("smart.disk.get", smart_json, value_type="4", itemid="20"),
        make_item(
            'wmi.getall[root\\microsoft\\windows\\storage,'
            '"SELECT FriendlyName, MediaType, BusType, Size, HealthStatus '
            'FROM MSFT_PhysicalDisk"]',
            wmi_json, value_type="4", itemid="21",
        ),
    ]

    result = storage.extract_storage(items)
    disks = result["physical_disks"]
    assert len(disks) == 3
    assert disks[0]["media_type"] == "NVMe"
    assert disks[0]["temperature_c"] == 37
    assert disks[1]["media_type"] == "HDD"
    assert disks[1]["bus_type"] == "SATA"
    assert disks[2]["media_type"] == "SSD"


def test_merges_top_directories_and_programs_per_volume():
    top_json = json.dumps({
        "C:": {
            "top_dirs": [{"path": "C:\\ProgramData", "bytes": 15 * 1024 ** 3}],
            "top_apps": [{
                "name": "SQL Server",
                "path": "C:\\Program Files\\MSSQL",
                "bytes": 10 * 1024 ** 3,
            }],
        },
        "D:": {
            "top_dirs": [{"path": "D:\\Backups", "bytes": 120 * 1024 ** 3}],
            "top_apps": [],
        },
    })
    items = [
        make_item('vfs.fs.size["C:",total]', str(100 * 1024 ** 3), "B", value_type="3", itemid="1"),
        make_item('vfs.fs.size["D:",total]', str(200 * 1024 ** 3), "B", value_type="3", itemid="2"),
        make_item("custom.disk.top_usage", top_json, value_type="4", itemid="3"),
        make_item('vfs.dir.size["C:\\inetpub\\logs"]', str(4 * 1024 ** 3), "B",
                  value_type="3", itemid="4"),
    ]

    result = storage.extract_storage(items)
    volumes = {v["volume"]: v for v in result["volumes"]}

    assert volumes["C:"]["top_dirs"][0]["path"] == "C:\\ProgramData"
    assert volumes["C:"]["top_apps"][0]["name"] == "SQL Server"
    assert volumes["D:"]["top_dirs"][0]["path"] == "D:\\Backups"
    # C: também recebeu o item nativo vfs.dir.size["C:\\inetpub\\logs"] não duplicado
    paths_c = [d["path"] for d in volumes["C:"]["top_dirs"]]
    assert "C:\\inetpub\\logs" in paths_c


def test_overview_summary_exposes_total_across_all_volumes():
    items = [
        make_item('vfs.fs.dependent.size["C:",pused]', "50", "%", itemid="1"),
        make_item('vfs.fs.dependent.size["C:",total]', str(100 * 1024 ** 3), "B",
                  value_type="3", itemid="2"),
        make_item('vfs.fs.dependent.size["D:",pused]', "25", "%", itemid="3"),
        make_item('vfs.fs.dependent.size["D:",total]', str(300 * 1024 ** 3), "B",
                  value_type="3", itemid="4"),
    ]
    record = {
        "items": items,
        "gauges": {"disk": {"itemid": "1", "lastclock": int(time.time())}},
    }
    summary = host_specs.overview_summary(record, int(time.time()))
    assert summary["disk_bytes"] == 100 * 1024 ** 3
    assert summary["disks_count"] == 2
    assert summary["disks_total_bytes"] == 400 * 1024 ** 3


def test_zabbix_storage_items_uses_zabbix_7_api_parameters(monkeypatch):
    captured = {}

    def fake_call(method, params=None, **kwargs):
        captured["method"] = method
        captured["params"] = params
        return []

    monkeypatch.setattr(zabbix, "call", fake_call)
    zabbix.storage_items("10084")

    assert captured["method"] == "item.get"
    params = captured["params"]
    assert params["hostids"] == ["10084"]
    assert params["filter"] == {"status": 0, "state": 0}
    assert params["searchByAny"] is True
    assert params["startSearch"] is True
    assert params["monitored"] is True
    assert "vfs.fs." in params["search"]["key_"]
    assert "smart.disk." in params["search"]["key_"]
    assert params["selectTags"] == ["tag", "value"]
    assert params["selectItemDiscovery"] == ["itemid", "parent_itemid"]
