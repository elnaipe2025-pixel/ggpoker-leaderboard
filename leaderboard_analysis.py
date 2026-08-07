#!/usr/bin/env python3

import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SNAPSHOTS_FILE = BASE_DIR / "leaderboard_snapshots.csv"
CHANGES_FILE = BASE_DIR / "leaderboard_changes.csv"


def read_snapshots():
    if not SNAPSHOTS_FILE.exists():
        raise FileNotFoundError(
            f"No existe {SNAPSHOTS_FILE}"
        )

    with SNAPSHOTS_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("leaderboard_snapshots.csv está vacío.")

    return rows


def write_changes(rows):
    # Agrupar por captura
    snapshots = defaultdict(list)

    for row in rows:
        snapshots[row["captured_at_utc"]].append(row)

    # Orden cronológico de las capturas
    timestamps = sorted(snapshots.keys())

    output = []

    previous_by_player = {}

    for timestamp in timestamps:
        current_rows = snapshots[timestamp]

        # Ordenar por posición
        current_rows.sort(
            key=lambda row: int(row["rank"])
        )

        for row in current_rows:
            player = row["player"]

            current_rank = int(row["rank"])
            current_points = Decimal(row["points"])

            previous = previous_by_player.get(player)

            if previous is None:
                previous_rank = ""
                previous_points = ""
                rank_change = ""
                points_change = ""
            else:
                previous_rank_value = int(previous["rank"])
                previous_points_value = Decimal(previous["points"])

                previous_rank = previous_rank_value
                previous_points = f"{previous_points_value:.2f}"

                # Positivo = sube posiciones.
                # Ejemplo: puesto 5 -> puesto 3 = +2
                rank_change = previous_rank_value - current_rank

                # Positivo = gana puntos.
                points_change = f"{current_points - previous_points_value:.2f}"

            output.append(
                {
                    "captured_at_utc": timestamp,
                    "rank": current_rank,
                    "player": player,
                    "points": f"{current_points:.2f}",
                    "previous_rank": previous_rank,
                    "previous_points": previous_points,
                    "rank_change": rank_change,
                    "points_change": points_change,
                }
            )

        # Esta captura pasa a ser la referencia para la siguiente.
        previous_by_player = {
            row["player"]: row
            for row in current_rows
        }

    with CHANGES_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:
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

        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(output)

    print(
        f"OK: análisis generado con {len(output)} registros"
    )
    print(f"Analysis CSV: {CHANGES_FILE}")


def main():
    rows = read_snapshots()
    write_changes(rows)


if __name__ == "__main__":
    main()
