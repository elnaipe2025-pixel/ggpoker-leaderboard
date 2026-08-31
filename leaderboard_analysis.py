import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path


INPUT_CSV = Path("leaderboard_snapshots.csv")
OUTPUT_CHANGES_CSV = Path("leaderboard_changes.csv")
OUTPUT_TRAFFIC_CSV = Path("leaderboard_traffic.csv")
OUTPUT_ACTIVITY_CSV = Path("leaderboard_activity.csv")


def load_snapshots():
    snapshots = []

    if not INPUT_CSV.exists():
        print(f"DEBUG: no existe {INPUT_CSV}")
        return snapshots

    print(f"DEBUG: leyendo {INPUT_CSV}")
    print(f"DEBUG: tamaño del archivo: {INPUT_CSV.stat().st_size} bytes")

    # utf-8-sig elimina automáticamente un posible BOM del primer encabezado.
    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames:
            # Limpiar encabezados
            reader.fieldnames = [
                field.strip() if field else field
                for field in reader.fieldnames
            ]

        print(f"DEBUG: encabezados CSV: {reader.fieldnames}")

        for row in reader:
            # Limpiar espacios de encabezados y valores
            clean_row = {}

            for key, value in row.items():
                clean_key = key.strip() if key else key
                clean_value = value.strip() if isinstance(value, str) else value
                clean_row[clean_key] = clean_value

            captured_at = (
                clean_row.get("captured_at_utc")
                or clean_row.get("captured_at")
                or ""
            ).strip()

            player = (
                clean_row.get("player")
                or clean_row.get("nickname")
                or ""
            ).strip()

            rank = (
                clean_row.get("rank")
                or clean_row.get("position")
                or ""
            )

            points = (
                clean_row.get("points")
                or clean_row.get("point")
                or "0"
            )

            if not captured_at:
                continue

            snapshots.append({
                "captured_at_utc": captured_at,
                "player": player,
                "rank": rank,
                "points": points,
            })

    return snapshots


def analyze_changes(snapshots):
    """
    Compara cada jugador con su aparición anterior.

    rank_change:
        positivo = sube puestos
        negativo = baja puestos

    points_change:
        diferencia de puntos respecto a la captura anterior.
    """

    previous = {}
    output = []

    snapshots = sorted(
        snapshots,
        key=lambda x: (
            x["captured_at_utc"],
            int(x["rank"]) if str(x["rank"]).isdigit() else 999999,
        ),
    )

    for row in snapshots:
        player = row["player"]

        if not player:
            continue

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

            # Positivo = sube puestos.
            # Negativo = baja puestos.
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
        newline="",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def analyze_traffic(snapshots):
    """
    Calcula métricas de actividad a partir de las capturas.

    Cada timestamp distinto representa una captura del leaderboard.

    Se generan dos niveles:

    1. Por hora
       - número de capturas
       - filas capturadas
       - jugadores únicos
       - promedio de filas por captura
       - máximo de filas por captura

    2. Por día
       - número de capturas
       - filas capturadas
       - jugadores únicos
       - promedio de filas por captura
       - máximo de filas por captura
    """

    # ---------------------------------------------------------
    # AGRUPAR FILAS POR CAPTURA
    # ---------------------------------------------------------

    by_snapshot = defaultdict(list)

    for row in snapshots:
        timestamp = row["captured_at_utc"]

        if timestamp:
            by_snapshot[timestamp].append(row)

    snapshot_metrics = []

    for timestamp, rows in sorted(by_snapshot.items()):
        try:
            dt = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            print(
                f"DEBUG: timestamp no válido ignorado: {timestamp}"
            )
            continue

        unique_players = {
            row["player"]
            for row in rows
            if row.get("player")
        }

        snapshot_metrics.append({
            "captured_at_utc": timestamp,
            "date": dt.date().isoformat(),
            "hour": dt.hour,
            "rows_captured": len(rows),
            "unique_players": len(unique_players),
        })

    # ---------------------------------------------------------
    # AGRUPACIÓN POR HORA
    # ---------------------------------------------------------

    hourly = defaultdict(
        lambda: {
            "snapshots": 0,
            "rows_captured": 0,
            "unique_players": set(),
            "rows_per_snapshot": [],
        }
    )

    # Para evitar recorrer todas las filas repetidamente,
    # guardamos los jugadores por timestamp.
    players_by_timestamp = {
        timestamp: {
            row["player"]
            for row in rows
            if row.get("player")
        }
        for timestamp, rows in by_snapshot.items()
    }

    for snapshot in snapshot_metrics:
        key = (
            snapshot["date"],
            snapshot["hour"],
        )

        data = hourly[key]

        data["snapshots"] += 1
        data["rows_captured"] += snapshot["rows_captured"]
        data["rows_per_snapshot"].append(
            snapshot["rows_captured"]
        )

        data["unique_players"].update(
            players_by_timestamp.get(
                snapshot["captured_at_utc"],
                set(),
            )
        )

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

    # ---------------------------------------------------------
    # AGRUPACIÓN POR DÍA
    # ---------------------------------------------------------

    daily = defaultdict(
        lambda: {
            "snapshots": 0,
            "rows_captured": 0,
            "unique_players": set(),
            "rows_per_snapshot": [],
        }
    )

    for snapshot in snapshot_metrics:
        date = snapshot["date"]

        data = daily[date]

        data["snapshots"] += 1
        data["rows_captured"] += snapshot["rows_captured"]
        data["rows_per_snapshot"].append(
            snapshot["rows_captured"]
        )

        data["unique_players"].update(
            players_by_timestamp.get(
                snapshot["captured_at_utc"],
                set(),
            )
        )

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
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

def analyze_activity(changes):
    """
    Mide la actividad real del leaderboard a partir de los cambios
    observados entre capturas.

    Métricas:
      - rank_changes: número de movimientos de posición
      - points_changes: número de jugadores que cambiaron puntos
      - active_players: jugadores que tuvieron algún cambio
      - total_activity: suma de movimientos de posición y cambios de puntos

    Se agregan por hora y por día.
    """

    hourly = defaultdict(
        lambda: {
            "rank_changes": 0,
            "points_changes": 0,
            "active_players": set(),
        }
    )

    daily = defaultdict(
        lambda: {
            "rank_changes": 0,
            "points_changes": 0,
            "active_players": set(),
        }
    )

    for row in changes:
        timestamp = row.get("captured_at_utc", "")
        player = row.get("player", "")

        if not timestamp:
            continue

        try:
            dt = datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            )
        except (ValueError, TypeError):
            continue

        date = dt.date().isoformat()
        hour = dt.hour

        rank_change = row.get("rank_change", "")
        points_change = row.get("points_change", "")

        # -------------------------------------------------
        # CAMBIO DE POSICIÓN
        # -------------------------------------------------

        has_rank_change = False

        try:
            if rank_change != "" and float(rank_change) != 0:
                has_rank_change = True
        except (ValueError, TypeError):
            pass

        # -------------------------------------------------
        # CAMBIO DE PUNTOS
        # -------------------------------------------------

        has_points_change = False

        try:
            if points_change != "" and float(points_change) != 0:
                has_points_change = True
        except (ValueError, TypeError):
            pass

        # -------------------------------------------------
        # AGREGACIÓN HORARIA
        # -------------------------------------------------

        hourly_key = (date, hour)

        if has_rank_change:
            hourly[hourly_key]["rank_changes"] += 1

        if has_points_change:
            hourly[hourly_key]["points_changes"] += 1

        if has_rank_change or has_points_change:
            if player:
                hourly[hourly_key]["active_players"].add(player)

        # -------------------------------------------------
        # AGREGACIÓN DIARIA
        # -------------------------------------------------

        if has_rank_change:
            daily[date]["rank_changes"] += 1

        if has_points_change:
            daily[date]["points_changes"] += 1

        if has_rank_change or has_points_change:
            if player:
                daily[date]["active_players"].add(player)

    output = []

    # -----------------------------------------------------
    # RESULTADOS POR HORA
    # -----------------------------------------------------

    for (date, hour), data in sorted(hourly.items()):

        total_activity = (
            data["rank_changes"]
            + data["points_changes"]
        )

        output.append({
            "period": "hour",
            "date": date,
            "hour": hour,
            "rank_changes": data["rank_changes"],
            "points_changes": data["points_changes"],
            "active_players": len(data["active_players"]),
            "total_activity": total_activity,
        })

    # -----------------------------------------------------
    # RESULTADOS POR DÍA
    # -----------------------------------------------------

    for date, data in sorted(daily.items()):

        total_activity = (
            data["rank_changes"]
            + data["points_changes"]
        )

        output.append({
            "period": "day",
            "date": date,
            "hour": "",
            "rank_changes": data["rank_changes"],
            "points_changes": data["points_changes"],
            "active_players": len(data["active_players"]),
            "total_activity": total_activity,
        })

    return output


def write_activity(rows):
    fieldnames = [
        "period",
        "date",
        "hour",
        "rank_changes",
        "points_changes",
        "active_players",
        "total_activity",
    ]

    with OUTPUT_ACTIVITY_CSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)
def main():
    print("DEBUG: buscando leaderboard_snapshots.csv")

    snapshots = load_snapshots()

    print(
        f"DEBUG: registros cargados: {len(snapshots)}"
    )

    if snapshots:
        print("DEBUG: primer registro:")
        print(snapshots[0])

    if not snapshots:
        raise ValueError(
            "No leaderboard snapshots found in "
            "leaderboard_snapshots.csv"
        )

    # =========================================================
    # 1. ANÁLISIS DE CAMBIOS DE JUGADORES
    # =========================================================

    changes = analyze_changes(snapshots)

    write_changes(changes)

    print(
        f"OK: análisis generado con {len(changes)} registros"
    )

    print(
        f"Analysis CSV: {OUTPUT_CHANGES_CSV}"
    )

    # =========================================================
    # 2. MÉTRICAS DE TRÁFICO
    # =========================================================

    traffic = analyze_traffic(snapshots)

    write_traffic(traffic)

    print(
        f"OK: métricas de tráfico generadas con "
        f"{len(traffic)} registros"
    )

    print(
        f"Traffic CSV: {OUTPUT_TRAFFIC_CSV}"
    )

    # =========================================================
    # 3. MÉTRICAS DE ACTIVIDAD
    # =========================================================

    activity = analyze_activity(changes)

    write_activity(activity)

    print(
        f"OK: métricas de actividad generadas con "
        f"{len(activity)} registros"
    )

    print(
        f"Activity CSV: {OUTPUT_ACTIVITY_CSV}"
    )


if __name__ == "__main__":
    main()
if __name__ == "__main__":
    main()
