from __future__ import annotations

from src.config import get_settings
from src.graph.factory import get_graph_store


def main() -> None:
    s = get_settings()

    print("Graph config:")
    print(f"  enabled  = {s.graph.enabled}")
    print(f"  provider = {s.graph.provider}")
    print(f"  uri      = {s.graph.uri}")
    print(f"  user     = {s.graph.user}")
    print(f"  database = {s.graph.database}")

    graph = get_graph_store(s)
    try:
        ok = graph.ping()
        print(f"\nPing success: {ok}")

        print("\nEnsuring schema...")
        graph.ensure_schema()
        print("Schema ensured successfully.")

    finally:
        graph.close()
        print("\nGraph connection closed.")


if __name__ == "__main__":
    main()