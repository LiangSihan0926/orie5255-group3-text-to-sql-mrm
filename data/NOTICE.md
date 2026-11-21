# BIRD financial data

`financial.sqlite.gz` is a compressed, byte-for-byte snapshot of the BIRD
development-set `financial` SQLite file bundled with the team's pilot. The
uncompressed SHA-256 is
`d15d89cdb068a202b6f2b99342af44dffc1d52545b39ceaf62efdc0ba570101e`.
The archive also preserves BIRD's column descriptions and the subset of
106 official financial development items. No rows were altered.

BIRD attribution goes to Jinyang Li and the BIRD team. The
[BIRD release page](https://bird-bench.github.io/) lists CC BY-SA 4.0
for the dataset. See the
[Creative Commons license](https://creativecommons.org/licenses/by-sa/4.0/)
and the [BIRD paper](https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html)
for dataset provenance, including its discussion of upstream sources.
The underlying historical Czech banking data is associated with the
Berka PKDD'99 discovery challenge.

The snapshot includes historical client attributes. Use it for this private
course evaluation. The verification outputs
contain aggregates or match flags. The pilot audit reads saved responses as
records. A separate paper-replication check executes only the two fixed SQL
examples printed in Figure 8 against the read-only snapshot and saves no
customer-level results.
