# Agent Skills for the David H. O'Connor (DHO) Lab

Each skill is a self-contained reference guide — a `SKILL.md` with YAML frontmatter
(`name`, `description`) in the portable [Agent Skills](https://agentskills.io/specification)
format. An AI coding agent loads a skill on demand when its trigger conditions match,
so lab-specific institutional knowledge doesn't have to be re-derived every time.

## Skills

| Skill                                              | Use it when                                                                                                                                                                                                                             |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`chtc-oconnor-jobs`](skills/chtc-oconnor-jobs/SKILL.md) | Running OConnor-group HTCondor batch campaigns on CHTC — staging large data, transferring execute-node inputs, packaging runtimes, starting with a canary, bounding concurrency, and retaining only verified outputs.              |
| [`dholk`](skills/dholk/SKILL.md)                   | Working with LabKey or the DHO Lab's DHOLK instance — exploring containers and schemas, writing queries or client scripts, and configuring MCP tools without committing API keys. The MCP tools are read-only, but generated scripts may not be. |
| [`duckdb-dholk`](skills/duckdb-dholk/SKILL.md)     | Analyzing DHOLK tables locally with DuckDB through `duck-lk`. This thin bridge depends on the `dholk` skill in this repository and the upstream [`duck-lk`](https://github.com/nrminor/duck-lk) skill.                              |
| [`nf-ospool`](skills/nf-ospool/SKILL.md)           | Setting up or debugging a Nextflow workflow on CHTC / OSPool with the `nf-ospool` executor plugin — instant-crash jobs, multi-day `condor_q`-empty hangs, `HasCHTCStaging` matchmaking, containers, and why `sharedFilesystem = false`. |
| [`nf-ospool-test`](skills/nf-ospool-test/SKILL.md) | Verifying a CHTC / OSPool setup actually works _before_ a long run — a live smoke test that submits one tiny probe job and confirms the staging path is healthy. Companion to `nf-ospool`.                                              |

## Installing

Use the [`skills`](https://github.com/vercel-labs/skills) installer and choose
which skills and coding agents you want to configure. Installation is local to
the current project by default; pass `--global` to install for your user account.

With npm:

```bash
npx skills@latest add dholab/skills
```

With pnpm:

```bash
pnpm dlx skills@latest add dholab/skills
```

With Bun:

```bash
bunx skills@latest add dholab/skills
```

To inspect the available skills without installing them:

```bash
npx skills@latest add dholab/skills --list
```

### Manual installation

Clone the repository, then link or copy each desired skill directory into the
folder your agent scans for skills:

- **Claude Code:** `~/.claude/skills/`
- **Codex:** `~/.codex/skills/`
- **GitHub Copilot CLI:** `~/.copilot/skills/`
- **Gemini CLI:** `~/.gemini/skills/`
- **OpenCode:** `~/.config/opencode/skills/`

```bash
git clone https://github.com/dholab/skills.git dholab-skills
cd dholab-skills

# Symlinks stay in sync when you pull repository updates. Set this path to the
# directory for your agent from the list above.
SKILLS_DIR=~/.claude/skills
mkdir -p "$SKILLS_DIR"
ln -s "$PWD/skills/chtc-oconnor-jobs" "$SKILLS_DIR/chtc-oconnor-jobs"
ln -s "$PWD/skills/dholk"          "$SKILLS_DIR/dholk"
ln -s "$PWD/skills/duckdb-dholk"   "$SKILLS_DIR/duckdb-dholk"
ln -s "$PWD/skills/nf-ospool"      "$SKILLS_DIR/nf-ospool"
ln -s "$PWD/skills/nf-ospool-test" "$SKILLS_DIR/nf-ospool-test"
```

To install independent copies instead, replace each `ln -s` command with `cp -R`.

The agent then exposes them by name (in Claude Code, as `/chtc-oconnor-jobs`,
`/dholk`, `/duckdb-dholk`, `/nf-ospool`, and `/nf-ospool-test`).

## Contributing

Add a new skill as `skills/<name>/SKILL.md` with YAML frontmatter (`name`,
`description`). Keep the `description` focused on _when_ to use the skill (start
with "Use when…"). See the existing skills for the house style.
