from time import time

import supabase_client


def main() -> None:
    now = time()
    episode_id = supabase_client.push_alert_episode(
        {
            "started_ts": now - 30,
            "last_updated_ts": now,
            "current_state": "Warning",
            "status": "active",
            "meta": {"source": "mock"},
        }
    )

    if episode_id is None:
        print("[Mock] Failed to create alert episode")
        return

    print(f"[Mock] Created alert episode id={episode_id}")

    transitions = [
        {"episode_id": episode_id, "ts": now - 30, "state": "Warning"},
        {"episode_id": episode_id, "ts": now - 10, "state": "High Alert"},
    ]

    for transition in transitions:
        ok = supabase_client.push_alert_transition(transition)
        status = "ok" if ok else "failed"
        print(f"[Mock] Transition {transition['state']} -> {status}")


if __name__ == "__main__":
    main()
