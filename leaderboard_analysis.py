import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path


INPUT_CSV = Path("leaderboard_snapshots.csv")
OUTPUT_CHANGES_CSV = Path("leaderboard_changes.csv")
OUTPUT_TRAFFIC_CSV = Path("leaderboard_traffic.csv")


def load_snapshots():
    snapshots = []

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            captured_at = row.get("captured_at_utc", "").strip()
            player = row.get("player", "").strip()

            if not captured_at:
                continue

            snapshots.append({
                "captured_at_utc": captured_at,
                "player": player,
                "rank": row.get("rank", ""),
                "points": row.get("points", row.get("point", "0")),
            })

    return snapshots


def analyze_changes(snapshots):
    """
    Mantiene el análisis histórico de posición y puntos.

    Para cada jugador comparamos su posición y puntos
    contra la captura anterior disponible.
    """

    previous = {}
    output = []

    # Orden cronológico
    snapshots = sorted(
        snapshots,
        key=lambda x: (
            x["captured_at_utc"],
            int(x["rank"]) if str(x["rank"]).isdigit() else 999999
        )
    )

    for row in snapshots:
        player = row["player"]

        try:
            rank = int(row["rank"])
        except (ValueError, TypeError):
            rank = 0

        try:
            points = float(row["points"])
        except (ValueError, TypeError):
            points = 0.0

        old = previous.get(player)

        if old is None:
            previous_rank = ""
            previous_points = ""
            rank_change = ""
            points_change = ""
        else:
            previous_rank = old["rank"]
            previous_points = old["points"]

            # Positivo = sube puestos
            # Negativo = baja puestos
            rank_change = previous_rank - rank

            points_change = points - previous_points

        output.append({
            "captured_at_utc": row["captured_at_utc"],
            "rank": rank,
            "player": player,
            "points": points,
            "previous_rank": previous_rank,
            "previous_points": previous_points,
            "rank_change": rank_change,
            "points_change": points_change,
        })

        previous[player] = {
            "rank": rank,
            "points": points,
        }

    return output


def write_changes(rows):
    fieldnames = [
        "captured_at_utc",
        "rank",
        "player",
        "points",
        "previous_rank",
        "previous_points",
        "rank_change",
        "points_change",
    ]

    with OUTPUT_CHANGES_CSV.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze_traffic(snapshots):
    """
    Genera métricas de tráfico a partir de las capturas.

    Una captura del leaderboard representa una consulta/observación
    del ranking en ese momento.

    Métricas:
      - snapshots
      - rows_captured
      - unique_players
      - avg_rows_per_snapshot
      - max_rows_per_snapshot
    """

    # Agrupar primero por timestamp exacto.
    by_snapshot = defaultdict(list)

    for row in snapshots:
        timestamp = row["captured_at_utc"]
        by_snapshot[timestamp].append(row)

    snapshot_metrics = []

    for timestamp, rows in sorted(by_snapshot.items()):
        unique_players = {
            row["player"]
            for row in rows
            if row["player"]
        }

        try:
            dt = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        snapshot_metrics.append({
            "captured_at_utc": timestamp,
            "date": dt.date().isoformat(),
            "hour": dt.hour,
            "rows_captured": len(rows),
            "unique_players": len(unique_players),
        })

    # -----------------------------------------
    # AGREGADO POR HORA
    # -----------------------------------------

    hourly = defaultdict(lambda: {
        "snapshots": 0,
        "rows_captured": 0,
        "unique_players": set(),
        "rows_per_snapshot": [],
    })

    for snapshot in snapshot_metrics:
        key = (
            snapshot["date"],
            snapshot["hour"],
        )

        hourly[key]["snapshots"] += 1
        hourly[key]["rows_captured"] += snapshot["rows_captured"]
        hourly[key]["rows_per_snapshot"].append(
            snapshot["rows_captured"]
        )

        # Buscar los jugadores de esa captura
        for row in snapshots:
            if row["captured_at_utc"] == snapshot["captured_at_utc"]:
                if row["player"]:
                    hourly[key]["unique_players"].add(row["player"])

    hourly_rows = []

    for (date, hour), data in sorted(hourly.items()):
        snapshots_count = data["snapshots"]

        avg_rows = (
            data["rows_captured"] / snapshots_count
            if snapshots_count
            else 0
        )

        max_rows = (
            max(data["rows_per_snapshot"])
            if data["rows_per_snapshot"]
            else 0
        )

        hourly_rows.append({
            "period": "hour",
            "date": date,
            "hour": hour,
            "snapshots": snapshots_count,
            "rows_captured": data["rows_captured"],
            "unique_players": len(data["unique_players"]),
            "avg_rows_per_snapshot": round(avg_rows, 2),
            "max_rows_per_snapshot": max_rows,
        })

    # -----------------------------------------
    # AGREGADO POR DÍA
    # -----------------------------------------

    daily = defaultdict(lambda: {
        "snapshots": 0,
        "rows_captured": 0,
        "unique_players": set(),
        "rows_per_snapshot": [],
    })

    for snapshot in snapshot_metrics:
        date = snapshot["date"]

        daily[date]["snapshots"] += 1
        daily[date]["rows_captured"] += snapshot["rows_captured"]
        daily[date]["rows_per_snapshot"].append(
            snapshot["rows_captured"]
        )

        for row in snapshots:
            if row["captured_at_utc"] == snapshot["captured_at_utc"]:
                if row["player"]:
                    daily[date]["unique_players"].add(row["player"])

    daily_rows = []

    for date, data in sorted(daily.items()):
        snapshots_count = data["snapshots"]

        avg_rows = (
            data["rows_captured"] / snapshots_count
            if snapshots_count
            else 0
        )

        max_rows = (
            max(data["rows_per_snapshot"])
            if data["rows_per_snapshot"]
            else 0
        )

        daily_rows.append({
            "period": "day",
            "date": date,
            "hour": "",
            "snapshots": snapshots_count,
            "rows_captured": data["rows_captured"],
            "unique_players": len(data["unique_players"]),
            "avg_rows_per_snapshot": round(avg_rows, 2),
            "max_rows_per_snapshot": max_rows,
        })

    return hourly_rows + daily_rows


def write_traffic(rows):
    fieldnames = [
        "period",
        "date",
        "hour",
        "snapshots",
        "rows_captured",
        "unique_players",
        "avg_rows_per_snapshot",
        "max_rows_per_snapshot",
    ]

    with OUTPUT_TRAFFIC_CSV.open(
        "w",
        encoding="utf-8",
        newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    snapshots = load_snapshots()

    if not snapshots:
        raise ValueError(
            "No leaderboard snapshots found in leaderboard_snapshots.csv"
        )

    # Análisis de jugadores
    changes = analyze_changes(snapshots)
    write_changes(changes)

    print(
        f"OK: análisis generado con {len(changes)} registros"
    )
    print(
        f"Analysis CSV: {OUTPUT_CHANGES_CSV}"
    )

    # Análisis de tráfico
    traffic = analyze_traffic(snapshots)
    write_traffic(traffic)

    print(
        f"OK: métricas de tráfico generadas con {len(traffic)} registros"
    )
    print(
        f"Traffic CSV: {OUTPUT_TRAFFIC_CSV}"
    )


if __name__ == "__main__":
    main()
