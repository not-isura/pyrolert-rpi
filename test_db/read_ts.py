from datetime import datetime

unix_ts = 1774779386
readable = datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")
print(readable)  # 2026-03-29 12:22:22