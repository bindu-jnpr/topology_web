import html
import json
import math
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database import DB_PATH, init_db
from generator import generate, modify
from schemas import Topology


def escape(value):
    return html.escape(str(value if value is not None else ""))


def table(headers, rows):
    heading = "".join(f"<th>{escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{escape(value)}</td>" for value in row)
        + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{heading}</tr></thead><tbody>{body}</tbody></table>"


def validate_references(topology):
    names = [device.name for device in topology.devices]

    if not names or len(names) != len(set(names)):
        raise ValueError("Topology must contain devices with unique names.")

    for device in topology.devices:
        if device.type not in {"SSR", "SRX", "EX", "AP"}:
            raise ValueError(f"Unsupported device type: {device.type}")

    for link in topology.links:
        if link.from_device not in names or link.to_device not in names:
            raise ValueError("A link references a device that does not exist.")


def diagram(topology):
    radius = max(220, len(topology.devices) * 40)
    center = radius + 120
    size = center * 2
    positions = {}

    for index, device in enumerate(topology.devices):
        angle = 2 * math.pi * index / len(topology.devices) - math.pi / 2
        positions[device.name] = (
            center + radius * math.cos(angle),
            center + radius * math.sin(angle),
        )

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="Network topology">'
    ]

    for index, link in enumerate(topology.links, 1):
        x1, y1 = positions[link.from_device]
        x2, y2 = positions[link.to_device]
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#64748b" stroke-width="2"/>'
            f'<text x="{(x1 + x2) / 2}" y="{(y1 + y2) / 2 - 8}" '
            f'text-anchor="middle" fill="#334155">L{index}</text>'
        )

    for device in topology.devices:
        x, y = positions[device.name]
        parts.append(
            f'<rect x="{x - 85}" y="{y - 32}" width="170" height="64" '
            f'rx="8" fill="#e0f2fe" stroke="#0284c7"/>'
            f'<text x="{x}" y="{y - 5}" text-anchor="middle">'
            f'{escape(device.name)}</text>'
            f'<text x="{x}" y="{y + 18}" text-anchor="middle">'
            f'{escape(device.type)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def render_report(topology_id, topology, history):
    devices = table(
        ["Device", "Type", "Router ID", "Loopback"],
        [
            [d.name, d.type, d.router_id, d.loopback]
            for d in topology.devices
        ],
    )

    links = table(
        ["Link", "From", "Interface", "IP", "To", "Interface", "IP", "OSPF area"],
        [
            [
                f"L{index}",
                link.from_device,
                link.from_iface,
                link.ip_from,
                link.to_device,
                link.to_iface,
                link.ip_to,
                link.ospf_area,
            ]
            for index, link in enumerate(topology.links, 1)
        ],
    )

    vlans = table(
        ["Device", "VLAN", "Name", "Subnet"],
        [
            [device.name, vlan.vlan_id, vlan.name, vlan.subnet]
            for device in topology.devices
            for vlan in device.vlans
        ],
    )

    tests = "".join(
        f"<li>{escape(test)}</li>" for test in topology.test_cases
    )

    audit = table(
        ["Action", "Instruction / feedback", "Time (UTC)", "Jenkins build"],
        [
            [event["action"], event["instruction"],
             event["created_at"], event["build_url"]]
            for event in history
        ],
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(topology.name)}</title>
<style>
body {{ font-family: sans-serif; max-width: 1200px; margin: 30px auto;
        padding: 0 20px; color: #172033; }}
h1, h2 {{ color: #0369a1; }}
svg {{ width: 100%; max-height: 650px; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 24px; }}
th, td {{ border: 1px solid #cbd5e1; padding: 9px; text-align: left;
          overflow-wrap: anywhere; white-space: pre-wrap; }}
th {{ background: #e0f2fe; }}
li {{ margin-bottom: 10px; }}
</style>
</head>
<body>
<h1>{escape(topology.name)}</h1>
<p><strong>Topology ID:</strong> {topology_id}</p>
<p><strong>Scenario:</strong> {escape(topology.scenario)}</p>
<p>AI-generated proposal: review device capabilities and test coverage before use.
Link numbers correspond to the link table; parallel links may overlap.</p>
<h2>Topology diagram</h2>
{diagram(topology)}
<h2>Devices</h2>
{devices}
<h2>Links</h2>
{links}
<h2>VLANs</h2>
{vlans}
<h2>Test cases</h2>
<ol>{tests}</ol>
<h2>Instruction and feedback history</h2>
{audit}
</body>
</html>
"""


def main():
    output = Path("reports")
    output.mkdir(exist_ok=True)

    for name in ("topology.html", "topology.json", "history.json"):
        (output / name).unlink(missing_ok=True)

    action = os.getenv("ACTION", "generate").strip().lower()
    scenario = os.getenv("SCENARIO", "").strip()
    instruction = os.getenv("INSTRUCTION", "").strip()
    parent_id = None

    if action not in {"generate", "modify", "good", "bad"}:
        raise SystemExit("ACTION must be generate, modify, good, or bad.")

    init_db()

    if action == "generate":
        if not scenario:
            raise SystemExit("Enter a scenario in SCENARIO.")
        topology = generate(scenario)
        instruction = scenario
    else:
        try:
            topology_id = int(os.getenv("TOPOLOGY_ID", ""))
        except ValueError:
            raise SystemExit("Enter a numeric TOPOLOGY_ID from an earlier report.")

        with sqlite3.connect(DB_PATH) as connection:
            saved = connection.execute(
                "SELECT scenario, topology_json FROM topologies WHERE id = ?",
                (topology_id,),
            ).fetchone()

        if saved is None:
            raise SystemExit(f"Topology {topology_id} was not found.")

        scenario, existing_json = saved

        if action == "modify":
            if not instruction:
                raise SystemExit("Enter the requested change in INSTRUCTION.")
            parent_id = topology_id
            topology = modify(
                existing_json,
                f"Original scenario: {scenario}\n"
                f"Requested change: {instruction}\n"
                "Preserve unrelated devices, connections, addressing, and test intent.",
            )
        else:
            topology = Topology.model_validate_json(existing_json)
            instruction = instruction or f"Rated {action}"

    validate_references(topology)
    now = datetime.now(timezone.utc).isoformat()

    # Save the version/feedback and its audit event in one transaction.
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS jenkins_topology_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topology_id INTEGER NOT NULL,
                parent_id INTEGER,
                action TEXT NOT NULL,
                instruction TEXT NOT NULL,
                build_url TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        if action in {"generate", "modify"}:
            cursor = connection.execute(
                """INSERT INTO topologies
                   (scenario, topology_json, created_at)
                   VALUES (?, ?, ?)""",
                (scenario, topology.model_dump_json(), now),
            )
            topology_id = cursor.lastrowid
        else:
            connection.execute(
                "UPDATE topologies SET feedback = ? WHERE id = ?",
                (1 if action == "good" else -1, topology_id),
            )

        connection.execute(
            """INSERT INTO jenkins_topology_events
               (topology_id, parent_id, action, instruction, build_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                topology_id,
                parent_id,
                action,
                instruction,
                os.getenv("BUILD_URL", ""),
                now,
            ),
        )

        connection.row_factory = sqlite3.Row
        history = [
            dict(row)
            for row in connection.execute(
                """
                WITH RECURSIVE lineage(topology_id) AS (
                    SELECT ?
                    UNION
                    SELECT event.parent_id
                    FROM jenkins_topology_events AS event
                    JOIN lineage ON event.topology_id = lineage.topology_id
                    WHERE event.parent_id IS NOT NULL
                )
                SELECT action, instruction, build_url, created_at
                FROM jenkins_topology_events
                WHERE topology_id IN (SELECT topology_id FROM lineage)
                ORDER BY id
                """,
                (topology_id,),
            )
        ]

    (output / "topology.html").write_text(
        render_report(topology_id, topology, history), encoding="utf-8"
    )
    (output / "topology.json").write_text(
        json.dumps(
            {"id": topology_id, "topology": topology.model_dump()},
            indent=2,
        ),
        encoding="utf-8",
    )
    (output / "history.json").write_text(
        json.dumps(history, indent=2), encoding="utf-8"
    )

    print(f"Action completed: {action}")
    print(f"Topology ID: {topology_id}")
    print("Reports saved in reports/")


if __name__ == "__main__":
    main()
