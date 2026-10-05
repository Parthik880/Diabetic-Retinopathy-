# RetinaGram architecture graph

Generated on 2026-10-05 from the portable native source and documentation using
official **graphifyy 0.9.53**. This map describes the implementation; historical
spec claims are identified as historical.

## Published artifacts

- `graph.json`: 1,201 nodes, 2,412 undirected edges, 67 named communities and
  3 documented group relationships.
- `GRAPH_REPORT.md`: hubs, connections, community cohesion, suggested questions
  and extraction diagnostics.
- `graph.html`: interactive graph; open locally in a browser, without a server.
- This README: provenance, limitations and regeneration instructions.

Source references are repository-relative. No interpreter, absolute root,
cache, cost tracker, manifest or temporary extraction state is published.

## Corpus and extraction

Detection found 80 files: 63 code files and 17 documents, about 70,192 words.
The graph excludes generated build/package data, checkpoint binaries and their
directory, images/font binaries, patient/session data and Graphify output itself.
Font license documents remain included. `.graphifyignore` records these rules.

The official AST extractor produced 1,099 nodes and 2,718 raw edges. A host agent
read all 17 detected documents and produced 102 semantic nodes, 218 edges and
3 hyperedges. That fragment has unique IDs and no dangling endpoints. Official
Graphify libraries combined, built, clustered and analyzed the extraction;
community names were selected from the extracted nodes. The official CLI exported
HTML and ran its retrieval benchmark. No relationship was added to repair a
parser gap or fabricate coverage.

## Limits and health

Four valid, successfully compiled C++ files have parser coverage gaps:

- `src/include/core/AppPaths.h`, line 10: no header symbols extracted; the
  implementation is extracted from `src/core/AppPaths.cpp`.
- `src/inference/stages/RuntimeSupport.cpp`, line 93: 24 symbols extracted.
- `tests/FunctionalSmoke.cpp`, line 24: 6 symbols extracted.
- `tests/UiRegression.cpp`, line 34: 9 symbols extracted.

The 2,936 combined raw edges contain **368 unresolved endpoint references**,
including external/import references. The undirected builder collapses 178
same-endpoint relations; the diagnostic also reports 174 directed collapses.
There are 50 exact duplicate raw records, zero missing endpoint fields and zero
self loops. The exported graph has **zero dangling endpoints**. These are
different checks: a usable exported graph does not make the extraction complete.
The report preserves the official diagnostic output. Inferred relationships
remain marked and need source verification; weakly connected nodes and generic
Qt types can limit navigation. This graph is an architectural aid.

Host semantic token usage is unavailable. Zero schema counters are placeholders
that exclude host-agent usage and do not establish zero cost. The official
benchmark estimates a 60,050-word corpus, about 80,066 naive tokens, an average
query of about 7,542 tokens and 10.6x reduction on its three generic questions.
Its corpus estimate differs from detection; this is a retrieval estimate, not
measured host usage or a model accuracy/runtime benchmark.

## Regeneration and navigation

Install the tested Graphify version and its Codex skill:

```bash
uv tool install graphifyy==0.9.53
graphify install --platform codex
```

From the repository root, ask a Graphify-capable host agent to run `/graphify .`.
Use the full skill workflow: corpus detection, official AST extraction,
source-grounded document semantics, official graph build/analysis, named
communities, diagnostics, report and HTML. `graphify update .` is a code update
command; it does not replace fresh semantic review of changed documentation.
Only overwrite the published graph intentionally after inspecting any shrink
guard and extraction warnings. Recreate local state in each clone rather than
copying machine-specific interpreter/root files.

For an existing published graph:

```bash
graphify query "How does model configuration reach the stage adapters?"
graphify god-nodes --top 10
graphify explain "AnalysisController"
graphify export html
graphify benchmark
```

Before publication, audit source paths, graph health and Git contents. Retain
only the four artifacts listed above. Follow the repository's AGENTS.md contracts.
