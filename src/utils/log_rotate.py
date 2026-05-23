from pathlib import Path

LOG_DIR = Path("logs")


def is_log_file(path: Path) -> bool:
    """Return True for active log files and rotated log backups."""
    return path.is_file() and (path.name.endswith(".log") or ".log." in path.name)


def iter_log_files(log_dir: Path = LOG_DIR) -> list[Path]:
    """Collect log files recursively inside the log directory."""
    if not log_dir.exists():
        return []

    return sorted(path for path in log_dir.rglob("*") if is_log_file(path))


def clear_log_file(path: Path) -> int:
    """Truncate a log file and return the number of reclaimed bytes."""
    reclaimed_bytes = path.stat().st_size
    path.write_text("", encoding="utf-8")
    return reclaimed_bytes


def rotate_log(log_dir: Path = LOG_DIR) -> None:
    """Clear all log files inside the log directory recursively."""
    log_dir.mkdir(parents=True, exist_ok=True)

    log_files = iter_log_files(log_dir)
    if not log_files:
        print(f"Nenhum arquivo de log encontrado em {log_dir}")
        return

    cleared_files = 0
    reclaimed_bytes = 0

    for log_file in log_files:
        reclaimed_bytes += clear_log_file(log_file)
        cleared_files += 1

    reclaimed_mb = reclaimed_bytes / (1024 * 1024)
    print(f"Logs limpos em {log_dir}: {cleared_files} arquivo(s), {reclaimed_mb:.2f} MB liberados.")


if __name__ == "__main__":
    rotate_log()
