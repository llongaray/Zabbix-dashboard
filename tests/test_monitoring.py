"""Regressões: métricas de rede e valores vazios do Zabbix."""
import time

from app.services.monitoring import gauge_metrics


def item(key, value, units="%", name="Item", clock=None, **overrides):
    return {
        "itemid": "42",
        "key_": key,
        "name": name,
        "lastvalue": value,
        "units": units,
        "value_type": "0",
        "status": "0",
        "lastclock": str(clock if clock is not None else int(time.time())),
        **overrides,
    }


def test_network_dropped_packets_cannot_be_traffic_rate():
    metrics = gauge_metrics([
        item("net.if.in[Ethernet 3,dropped]", "0", "bps",
             "Inbound packets discarded"),
    ])
    assert "network_in" not in metrics


def test_network_byte_counter_is_not_bandwidth():
    metrics = gauge_metrics([item("net.if.in[eth0,bytes]", "500000", "B")])
    assert "network_in" not in metrics


def test_network_bps_converted_to_mbps():
    metrics = gauge_metrics([
        item("net.if.in[eth0,bytes]", "2000000", "bps",
             "Interface eth0 bits received"),
    ])
    assert metrics["network_in"]["value"] == 2
    assert metrics["network_in"]["units"] == "Mbps"


def test_network_bytes_per_second_converted_to_megabits():
    metrics = gauge_metrics([
        item("net.if.out[eth0,bytes]", "125000", "Bps",
             "Interface eth0 traffic"),
    ])
    assert metrics["network_out"]["value"] == 1


def test_empty_cpu_is_not_zero():
    metrics = gauge_metrics([item("system.cpu.util", "", "%", "CPU utilization")])
    assert "cpu" not in metrics


def test_cpu_idle_percentage_is_not_total_cpu_usage():
    metrics = gauge_metrics([item("system.cpu.util[,idle]", "90", "%")])
    assert "cpu" not in metrics


def test_valid_cpu_percentage():
    metrics = gauge_metrics([item("system.cpu.util", "11.3", "%")])
    assert metrics["cpu"]["value"] == 11.3


def test_memory_percentage():
    metrics = gauge_metrics([item("vm.memory.size[pused]", "72.5", "%")])
    assert metrics["memory"]["value"] == 72.5


def test_stale_value_is_flagged():
    metrics = gauge_metrics([item("system.cpu.util", "13", "%",
                                  clock=int(time.time()) - 7200)])
    assert metrics["cpu"]["stale"] is True
