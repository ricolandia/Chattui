# chattui

> [🇧🇷 Português (README.md)](README.md) · 🇺🇸 **English (this file)**

A TUI (terminal UI) chat client in Python + [Textual](https://github.com/Textualize/textual) —
in the spirit of Elia, but yours: easy to dig into and change whenever you want.

Talks to any OpenAI-compatible API: Ollama, LocalAI, OpenAI, your own VPS, etc.
Includes local RAG, persistent memory and Python plugins.

## Install

```bash
pip install -r requirements.txt --break-system-packages   # or inside a venv
mkdir -p config
cp config.example.toml config/config.toml
```

The whole folder is self-contained — `config/`, `plugins/` and `data/`
(created automatically) live inside it, so copying/distributing is just
copying the folder. Nothing depends on `~/.config` or `~/.local`.

Edit `config/config.toml` with your endpoints. If a model needs a key,
export the matching environment variable before running (e.g.
`export CHATTUI_VPS_KEY=...`) — never put the key in the config file.

## Run

```bash
python3 chattui.py
```

## Shortcuts

| Key       | Action                                   |
|-----------|------------------------------------------|
| Enter     | send message                             |
| Ctrl+N    | new conversation                          |
| Ctrl+M    | switch model/endpoint                     |
| Ctrl+R    | toggle RAG for this session               |
| Ctrl+D    | delete current conversation (asks confirmation) |
| Esc       | cancel the ongoing generation             |
| Ctrl+J    | jump to the end of the chat (re-enables follow-scroll) |
| Ctrl+Y    | copy the last answer to the system clipboard |
| Ctrl+P    | command palette (search `/commands` without memorizing them) |
| Ctrl+Q    | quit                                      |

The scroll follows the streamed answer while you're at the bottom of the
chat; scroll up to re-read and it freezes on its own, resuming when you go
back down (or with Ctrl+J).

## Commands (type them in the input box)

> The slash commands are Portuguese by design (the app's default language):
> `criar` = create, `ver` = list sources, `usar` = use, `todas` = all.

| Command | What it does |
|---|---|
| `/remember <text>` | stores a permanent fact in memory |
| `/memories` | lists saved memories (with id) |
| `/forget <id>` | deletes a memory |
| `/rag on` \| `/rag off` | toggles RAG usage for this session |
| `/rag_add <file>` | indexes a `.txt`/`.md` into the RAG (optional: `--lib <name>`) |
| `/rag_libs` | lists RAG libraries (chunks per lib + active one) |
| `/rag_lib usar <lib>` | filters search to that library (`todas` = all → no filter) |
| `/rag_lib criar <lib>` | creates (and activates) an empty library |
| `/rag_lib ver <lib>` | lists the files indexed in a library |
| `/rag_stats` | shows how many chunks/sources are indexed |
| `/rag dupes` | finds **semantically** near-duplicate chunks (doc×doc, no re-embedding) |
| `/notes` | lists the latest `.md` notes saved by tools |
| `/rename <title>` | renames the current conversation |
| `/export md [path]` | saves the conversation as `.md` (default: `data/exports/`; optional custom path) |
| `/export trilium` | sends the conversation to **today's daily note** in Trilium (Journal), raw markdown appended |
| `/plugins` | lists loaded plugins (and load errors) |
| `/idioma pt` \| `/idioma en` | switches the interface language at runtime (alias: `/language`) |

The interface is **Portuguese by default** and can be switched to
**English**: the startup language is set by `[geral] lang = "pt" | "en"` in
`config.toml`; at runtime use `/idioma en` (or `/language en`). The typed
commands stay the same in both languages (the `/rag_lib` sub-verbs also
accept `use`/`create`/`list` and `all`).

No need to memorize the list: `Ctrl+P` opens the command palette — commands
that take arguments (`/rag_add`, `/rename`, `/remember`, `/export md`…)
pre-fill the input box so you can complete the typing.

### Exporting (`.md` and Trilium)

`/export md` produces markdown with frontmatter (title/model/date) and
`## User` / `## Assistant` sections. Without an argument it saves to
`data/exports/` (self-contained); with an argument it saves to the given
path (`/export md ~/docs/chat.md` — the extension becomes `.md` on its own).

`/export trilium` appends the conversation to **today's daily note** in your
Trilium Journal (same convention as the `trilium_agenda_diaria.py` homelab
script: note `DD - Weekday name` under the Journal root; creates it if
missing). Requires `TRILIUM_URL` and `TRILIUM_TOKEN` in `.env`; the Journal
root is configurable via `TRILIUM_JOURNAL_ROOT` (default: the homelab one).

## API keys (.env)

```bash
cp .env.example .env
```

Fill `.env` with your keys. chattui reads this file on startup with its own
~15-line reader (no `python-dotenv` dependency) — nothing to export in the
shell. If the variable is already exported in the environment, the manual
export always wins over `.env` (standard dotenv behavior). `.env` is in
`.gitignore`, so there's no risk of accidentally committing a key.

## Sessions and history

Every conversation in the sidebar is a "session": saved on its own in
`data/history.db` (SQLite), remembering which model was used. There's no
manual "save" step — it's automatic on every message.

## Memory

Memory is different from history: it's facts you want **every** new
conversation to already know, without re-explaining. It's re-injected as a
system message on every call — hence the character budget
(`MAX_MEMORY_CHARS` in `memory.py`, currently 2000) which drops the oldest
entries before running out of room. Without that cap, memory would recreate
exactly the token-burn problem that motivated this project.

## Semantic memory (upsert)

With an embeddings endpoint configured (an `[embeddings]` section — or the
`[rag]` one, if present), `/remember` compares the new fact against the
stored ones and, if **similar** (cosine ≥ 0.90), **updates** the entry
instead of duplicating. Older facts without an embedding get one on first
use (automatic backfill).

```
/remember likes drip coffee        # saves
/remember prefers drip coffee      # ~updates the same entry
```

Without an embeddings endpoint, `/remember` keeps the simple
append behavior. If embedding fails, the fact is still saved and the chat
warns about it.

## Per-model parameters and instructions

Each `[[models]]` block in `config.toml` accepts optional fields:

| Field | What it does |
|---|---|
| `system_prompt` | fixed behavior instruction — becomes the 1st system message of every call to that model. Works on **any** endpoint (on Ollama the equivalent is embedding it in a Modelfile; here it also applies to OpenAI/OpenRouter) |
| `max_tool_hops` | tool round-trip limit per message (default 4) |
| `max_history_chars` | conversation history budget (characters). Older messages are trimmed before sending; the last question is never cut. `system_prompt`, memory and RAG do **not** count toward the budget |
| `temperature`, `top_p`, `seed`, `max_tokens` | standard OpenAI sampling |
| `frequency_penalty`, `presence_penalty`, `stop` | also standard OpenAI |

Example:

```toml
[[models]]
name = "ollama-3"
api_base = "http://127.0.0.1:11434/v1"
model_id = "llama3.2"
api_key_env = ""
system_prompt = "Answer in Portuguese. If you don't know, say you don't know — don't make things up."
max_history_chars = 12000
temperature = 0.7
max_tokens = 1024
```

> **num_ctx / repeat_penalty (Ollama):** they don't exist in the
> OpenAI-compatible API — Ollama silently ignores them on `/v1`. To give a
> local model more context, create a variant and use it as `model_id`:
>
> ```dockerfile
> FROM llama3.2
> PARAMETER num_ctx 8192
> ```
>
> ```bash
> ollama create mymodel-ctx8k
> ```
>
> Combine with `max_history_chars` above: chattui then sends a history that
> fits in the variant's `num_ctx`.

## Automatic notes (search becomes RAG by itself)

Every time a tool (plugin) runs, its result is saved as a `.md` in
`data/notes/` — no asking. If `[rag]` is configured in `config.toml`, the
note is indexed right away automatically, so every search you do in the chat
keeps growing your RAG base with zero manual steps. `/notes` shows the
latest ones.

Empty, error or too-short results (under 40 characters) are not indexed —
they only become files, without polluting similarity search later (see
`notes.py::is_indexable` to tune that filter).

This applies to any plugin, not just web search: a video transcript, a text
summary, extracted keywords — everything becomes a note and enters the RAG.

## RAG

Requires an embedding model running somewhere (simplest:
`ollama pull nomic-embed-text`) and numpy (optional dependency):

```bash
pip install -r requirements-rag-opcional.txt --break-system-packages
```

Configure `[rag]` in `config.toml`.

```
/rag_add ~/notes/project-x.txt
/rag on
```

From then on, every message retrieves the `top_k` most similar chunks and
injects them as context — no chromadb, no langchain: SQLite stores the
vectors (source of truth) and the normalized matrix lives in files
(`rag.db.matrix.npy` + `rag.db.ids.npy` + `rag.db.meta.json`) read via
`np.memmap` — the OS pages data in on demand during search and releases it
under memory pressure, so **the RAG doesn't hold the base in RAM when idle**
(great for lean hosts). `/rag_stats` shows the matrix size on disk.

### Libraries (organize by topic/project)

Each chunk belongs to a **library** (`lib`, default `geral`/`general`). The
app subtitle shows the active library while RAG is on; with no library
chosen the search scans **all** of them (default behavior).

```
/rag_add ~/notes/x.md --lib project-y    # creates the library and indexes into it
/rag_libs                                # lists libraries + chunk counts
/rag_lib usar project-y                  # search only that library ("todas" = all goes back)
/rag_lib criar nova                       # creates an empty library and activates it
/rag_lib ver project-y                   # files inside the library
```

The active library is per-session only (gone on exit). Deduplication is
**per library+source**: re-indexing the same file into the same library
doesn't duplicate; using the same source in another library is allowed (the
same base in two collections).

Duplicates from the same source in the same library are not re-indexed
(SHA-1 hash per chunk): repeating `/rag_add` on the same file doesn't
pollute the base.

Beyond the hash (exact text), **`/rag dupes`** compares the stored
vectors (doc×doc, no re-embedding) and groups chunks from **different
sources** that say the same thing in other words:

```
/rag dupes                       # all libraries, threshold 0.92
/rag dupes --lib project-x       # within one library
/rag dupes --limiar 0.95 --max 5 # stricter, top 5 groups
```

Pairs from the same source (e.g. the same file mirrored into two
libraries) are ignored — the goal is finding duplicates across distinct
files so you can remove the redundant source (removal itself is still
manual).

If anything goes wrong with the files (or you change embedding models),
delete the three `rag.db.{matrix.npy,ids.npy,meta.json}` — the next search
rebuilds everything from the SQLite BLOBs.

Today it only reads `.txt`/`.md` directly. To index PDF/DOCX, also install
`pypdf`/`python-docx` (already listed in `requirements-rag-opcional.txt`)
and adapt the loader in `rag.py::add_file` to extract text before chunking.

## Plugins (Python scripts as tools)

Any `.py` in `plugins/` exposing `TOOL_SCHEMA` + `run()` becomes a tool the
model can call. The example plugins ship ready in that folder (if one fails
to load, the app warns you in `/plugins`):

| Plugin | What it does | Dependency |
|---|---|---|
| `web_search.py` | web search by **term** | `ddgs` |
| `fetch_page.py` | downloads and reads the text of a **specific URL** | `requests` + `beautifulsoup4` + `lxml` |
| `youtube_transcript.py` | fetches a video's transcript | `youtube-transcript-api` |
| `summarize_text.py` | summarizes text (extractive, no LLM) | `sumy` + NLTK data |
| `extract_keywords.py` | extracts keywords | `yake` |
| `trilium_note.py` | creates a note in Trilium (requires `TRILIUM_URL`/`TRILIUM_TOKEN` envs) | `requests` |
| `buscar_trilium.py` | searches and reads Trilium notes (ETAPI) — chainable: search → `note_id` | `requests` + Trilium envs |
| `buscar_sessoes.py` | searches past opencode session logs (FTS) | stdlib (local `indice-memoria.py` index) |
| `agendar_evento.py` | creates an event in a Radicale/CalDAV calendar or lists the next 90 days | reuses a local `agendar.py` (`requests`) |
| `ler_arquivo_local.py` | reads/summarizes local files (.txt/.md/.csv/**.pdf**/**.docx**) | `pypdf` + `python-docx` (rag-optional) for PDF/DOCX |
| `_molde_script_existente.py` | template for wrapping one of your own scripts — not a real plugin | — |

The `agendar_evento` and `buscar_sessoes` plugins wrap scripts that
already exist on your machine (`agendar.py` for CalDAV and
`buscar-memoria.py` for session search) via subprocess — no duplicated
logic. Set `CHATTUI_SCRIPTS_PY` in `.env` pointing to that scripts
folder (chattui injects the env into plugins); without it, both return a
helpful error.

Install the dependencies of the plugins you plan to use:

```bash
pip install -r requirements-plugins-opcionais.txt --break-system-packages
python3 -c "import nltk; nltk.download('punkt_tab')"   # only for summarize_text
```

To disable a plugin, delete the file or rename it with a leading `_`
(files starting with `_` are ignored by the loader).

Because tool calling runs in a loop (up to `MAX_TOOL_HOPS` round trips),
the model can chain tools: ask for a video transcript and then summarize
it, all in a single message.

**Important:** tool calling only works if your model supports it (e.g.
`qwen2.5`, `llama3.1`, `mistral-nemo` on Ollama — `gemma3`, at any size,
does **not**). If the model doesn't support it, the app detects the error,
warns you and falls back to a normal answer without tools — the chat never
locks up.

**`web_search` searches by term, `fetch_page` reads a specific URL.** For
"what is website X" or a direct link, `fetch_page` is the right tool — a
text search over a poorly indexed domain usually returns little or nothing,
and smaller local models (e.g. 4B–7B) tend to fill that gap with general
knowledge instead of admitting they found nothing. The app already sends a
system instruction discouraging that when tools are active, but small
models may still do it — if you notice answers that are "almost right but
off-topic", suspect that before suspecting the plugin.

## Keeping it running on a server (persistent across SSH sessions)

```bash
tmux new -s chat
python3 chattui.py
# Ctrl+b, then d to "leave" without killing the process
# later, from anywhere:
tmux attach -t chat
```

## Where to dig if you want to extend it

- `chattui.py::ChatTUI._build_payload_messages` — builds the context
  (memory + RAG + history) before each call. Natural entry point to add
  more context sources.
- `chattui.py::ChatTUI._run_turn` — the tool-calling loop. `MAX_TOOL_HOPS`
  at the top of the file limits how many tool round trips happen per
  message.
- `memory.py` / `rag.py` / `plugins.py` — each is a small, independent
  module; any of them can be read end to end in a few minutes.

## Known limitations (a starting point, not Elia)

- No image/attachment support.
- RAG reads only `.txt`/`.md` by default (PDF/DOCX require the optional
  step above).
- History trimming is naive by design: the whole conversation is sent on
  every message (now workable around — set `max_history_chars` per model to
  trim the oldest messages before sending).
- Tool calling makes one non-streamed call to decide whether to use tools,
  and only then streams the final answer — slightly slower than plain chat,
  but avoids parsing fragmented tool calls inside the stream.
