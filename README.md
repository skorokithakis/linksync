# linksync

Two-way bookmark sync between [Linkora](https://github.com/nicefiction/linkora-sync-server) and [Readeck](https://readeck.org).

## Deployment

### Docker (recommended)

Copy `config/config.toml` and fill in your server URLs and tokens:

```toml
[linkora]
url = "http://linkora:45454"
token = "your-linkora-token"
verify_tls = false

[readeck]
url = "https://readeck.example.com"
token = "your-readeck-token"

[sync]
state_db = "/data/state.db"
folder_name = "Read later"
```

Then run with Docker Compose:

```bash
docker compose up -d
```

By default, it syncs every 5 minutes. Override the interval (in seconds) in `docker-compose.yml`:

```yaml
services:
  linksync:
    build: .
    restart: unless-stopped
    command: ["--interval", "60"]
    volumes:
      - ./config:/config:ro
      - linksync-data:/data

volumes:
  linksync-data:
```

### Manual

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/bin/pip install .
```

Create `~/.config/linksync/config.toml` (same format as above, but use `state_db = "~/.local/share/linksync/state.db"`).

One-shot sync:

```bash
.venv/bin/python -m linksync
```

Loop mode:

```bash
.venv/bin/python -m linksync --interval 300
```

Or run via cron:

```
*/5 * * * * /path/to/.venv/bin/python -m linksync
```
