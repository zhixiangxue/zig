# zig
Zeitro information graph

## Local FalkorDB with Docker

For local E2E development, run FalkorDB with Docker Desktop.

### 1. Start FalkorDB

```bash
docker run --rm -d \
  --name zig-falkordb-e2e \
  -p 6379:6379 \
  -p 3000:3000 \
  falkordb/falkordb:latest
```

This starts:

- **FalkorDB / Redis endpoint**: `localhost:6379`
- **FalkorDB Web UI**: `http://localhost:3000`

### 2. Run the E2E example

```bash
uv run python examples/e2e_falkordb.py
```

The example connects to:

```python
Graph("falkordb://localhost:6379/programs")
```

### 3. Open the Web UI

Open `http://localhost:3000` in your browser.

Useful Cypher queries:

```cypher
MATCH (n) RETURN n
```

```cypher
MATCH (p:Program)-[r:OFFERED_BY]->(a:Agency)
RETURN p, r, a
```

### 4. Stop FalkorDB

```bash
docker stop zig-falkordb-e2e
```
