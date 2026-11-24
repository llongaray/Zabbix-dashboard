"""Endpoints de leitura para relatórios operacionais."""
import csv
from datetime import datetime, timezone
from io import StringIO

from flask import Response, jsonify, request

from app.routes import bp
from app.routes.decorators import protected
from app.services import reports


def identifier(value):
    if value and (not value.isascii() or not value.isdecimal() or len(value) > 20):
        raise ValueError("Identificador inválido.")
    return value


def csv_text(value):
    # Nomes provenientes do Zabbix são texto, inclusive em planilhas.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


@bp.get("/api/reports/incidents")
@protected
def incident_report():
    days = int(request.args.get("days", 30))
    if days not in (7, 30, 90):
        raise ValueError("Selecione 7, 30 ou 90 dias.")
    group_id = identifier(request.args.get("group"))
    severity = request.args.get("severity")
    if severity not in (None, "", "0", "1", "2", "3", "4", "5"):
        raise ValueError("Severidade inválida.")
    tag = request.args.get("tag", "").strip()
    if len(tag) > 255:
        raise ValueError("Tag muito longa.")
    result = reports.incidents(days, group_id, int(severity) if severity else None, tag)
    if request.args.get("format") != "csv":
        return jsonify(result)
    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Problema", "Hosts", "Severidade", "Abertura UTC",
                     "Resolvido", "Segundos até reconhecer", "Segundos até recuperar", "Relatório parcial"])
    for row in result["rows"]:
        writer.writerow([row["id"], csv_text(row["name"]), csv_text(row["hosts"]), row["severity"],
                         datetime.fromtimestamp(row["opened_at"], timezone.utc).isoformat(),
                         "Sim" if row["resolved"] else "Não", row["ack_seconds"], row["recovery_seconds"],
                         "Sim" if result["truncated"] else "Não"])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv", headers={
        "Content-Disposition": 'attachment; filename="incidentes-zabbix.csv"',
    })


@bp.get("/api/reports/slas")
@protected
def sla_list():
    return jsonify(reports.sla_catalog())


@bp.get("/api/reports/slas/<sla_id>")
@protected
def sla_report(sla_id):
    return jsonify(reports.availability(identifier(sla_id)))


@bp.get("/api/reports/collection")
@protected
def collection_report():
    return jsonify(reports.collection_health())
