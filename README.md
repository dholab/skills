# dholab-skills

Shared **agent skills** for the O'Connor Lab (DHO).

Each skill is a self-contained reference guide — a `SKILL.md` with YAML frontmatter
(`name`, `description`) in the portable [Agent Skills](https://agentskills.io/specification)
format. An AI coding agent loads a skill on demand when its trigger conditions match,
so lab-specific institutional knowledge doesn't have to be re-derived every time.

The skill *content* here is not tied to any one agent — it's general CHTC / OSPool /
Nextflow knowledge. The `SKILL.md` format is recognized by Claude Code and other
compatible agents (Codex, Copilot CLI, Gemini CLI).

## Skills

| Skill | Use it when |
|---|---|
| [`nf-ospool`](skills/nf-ospool/SKILL.md) | Setting up or debugging a Nextflow workflow on CHTC / OSPool with the `nf-ospool` executor plugin — instant-crash jobs, multi-day `condor_q`-empty hangs, `HasCHTCStaging` matchmaking, containers, and why `sharedFilesystem = false`. |
| [`nf-ospool-test`](skills/nf-ospool-test/SKILL.md) | Verifying a CHTC / OSPool setup actually works *before* a long run — a live smoke test that submits one tiny probe job and confirms the staging path is healthy. Companion to `nf-ospool`. |

## Installing

Make the skills discoverable to your agent by linking or copying each skill
directory into the folder that agent scans for skills:

- **Claude Code:** `~/.claude/skills/`
- **Other agents (Codex, Copilot CLI, Gemini CLI):** `~/.agents/skills/` (cross-runtime alias)

```bash
git clone git@github.com:dholab/dholab-skills.git
cd dholab-skills

# Symlink into your agent's skills dir (recommended — stays in sync with git pulls).
# Swap ~/.claude/skills for ~/.agents/skills if you use a different agent:
SKILLS_DIR=~/.claude/skills
mkdir -p "$SKILLS_DIR"
ln -s "$PWD/skills/nf-ospool"      "$SKILLS_DIR/nf-ospool"
ln -s "$PWD/skills/nf-ospool-test" "$SKILLS_DIR/nf-ospool-test"
```

The agent then exposes them by name (in Claude Code, as `/nf-ospool` and
`/nf-ospool-test`).

## Contributing

Add a new skill as `skills/<name>/SKILL.md` with YAML frontmatter (`name`,
`description`). Keep the `description` focused on *when* to use the skill (start
with "Use when…"). See the existing skills for the house style.
