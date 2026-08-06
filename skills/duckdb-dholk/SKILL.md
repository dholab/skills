---
name: duckdb-dholk
description: Use when analyzing DHO Lab DHOLK tables locally with DuckDB through duck-lk — especially large or repeatedly queried LabKey tables, local Parquet synchronization, joins and exploratory analysis, or deciding how DHOLK container and credential context maps into the duck-lk workflow.
license: MIT
compatibility: Requires DuckDB, authorized DHOLK access with a Reader API key, the dholk skill from this repository, the duck-lk skill from nrminor/duck-lk, and approval to cache the selected data on local disk.
---

# duckdb-dholk

## Start with the companion skills

This is a coordinator, not a second copy of either dependency:

```text
dholk   → DHOLK server, containers, metadata discovery, and credential safety
duck-lk → DuckDB extension setup, synchronization, cache behavior, and analysis
```

Invoke both `dholk` and `duck-lk` before continuing. Their current instructions must be present in context; do not reconstruct a missing skill from memory or substitute this bridge for it.

If either skill is unavailable, stop and help the user install it. First ask which package runner is already available; do not assume npm or ask the user to install another package manager just for this task.

| Runner | Requirement | Install `dholk` | Install `duck-lk` |
|---|---|---|---|
| npm | Node.js with npm (`npx`) installed | `npx skills@latest add dholab/skills --skill dholk` | `npx skills@latest add nrminor/duck-lk --skill duck-lk` |
| pnpm | pnpm installed | `pnpm dlx skills@latest add dholab/skills --skill dholk` | `pnpm dlx skills@latest add nrminor/duck-lk --skill duck-lk` |
| Bun | Bun installed | `bunx skills@latest add dholab/skills --skill dholk` | `bunx skills@latest add nrminor/duck-lk --skill duck-lk` |

`npx` is available only when npm is installed. If none of these runners is available, direct the user to the [`dholk` source](https://github.com/dholab/skills/blob/main/skills/dholk/SKILL.md) and the upstream [`duck-lk` source](https://github.com/nrminor/duck-lk/blob/main/skills/duck-lk/SKILL.md) for manual installation into their agent's skills directory. Resume only after both skills are available and loaded.

## Hand off the DHOLK source

Use `dholk` to establish the source context that `duck-lk` needs:

- the confirmed DHOLK container, selected from the many containers under `/dho/projects/`;
- the discovered schema and query/table name;
- a dedicated Reader key available as `DHOLK_READER_API_KEY`;
- the intended analysis and output destination.

Do not guess container, schema, or query names from the small set of documented DHOLK landmarks. Use the `dholk` workflow to ask or discover them.

`duck-lk` expects `LABKEY_BASE_URL`, `LABKEY_CONTAINER`, and `LABKEY_API_KEY`. Scope the DHOLK mapping to the DuckDB process rather than exporting a second API-key variable across the agent's whole shell session:

```bash
LABKEY_BASE_URL='BASE_URL_FROM_DHOLK' \
LABKEY_CONTAINER='CONTAINER_FROM_DHOLK' \
LABKEY_API_KEY="${DHOLK_READER_API_KEY:?DHOLK_READER_API_KEY is not set}" \
duckdb
```

Replace the two sentinel values with context supplied by `dholk`, and have `duck-lk` supply the current non-interactive DuckDB arguments and SQL in place of the bare `duckdb` invocation. The shell text contains only a reference to the Reader key, not its value. Continue to follow the `dholk` credential boundary: do not print the variables or place token literals in project files, SQL, notebooks, chat, logs, or diffs.

## Apply the local-data gate

`duck-lk` can materialize DHOLK data into a local cache. Before allowing its workflow to synchronize anything, use the current `duck-lk` guidance to determine what will be copied, then confirm:

- applicable lab data-governance and PHI policy permits the data on this machine;
- local disk can hold the synchronized data and expected intermediates;
- outputs and exports have an approved destination;
- cached and derived data have an appropriate retention and cleanup plan.

If scope, size, policy, or destination is unknown, pause at metadata discovery. Once the gate passes, defer extension installation, synchronization decisions, cache operations, and DuckDB query patterns entirely to `duck-lk`.

## Completion check

- Both `dholk` and `duck-lk` were invoked and their current guidance is in context.
- Container, schema, and query names were confirmed from DHOLK metadata.
- The API key remained behind a process-scoped `DHOLK_READER_API_KEY` → `LABKEY_API_KEY` mapping.
- Local synchronization passed the policy, capacity, destination, and retention gate.
- DuckDB and `duck-lk` mechanics came from the upstream skill rather than this bridge.
- Cached data, exports, and derived files have an approved destination and retention plan.

## References

- [`duck-lk` upstream skill](https://github.com/nrminor/duck-lk/blob/main/skills/duck-lk/SKILL.md)
- [`dholk` companion skill](https://github.com/dholab/skills/blob/main/skills/dholk/SKILL.md)
