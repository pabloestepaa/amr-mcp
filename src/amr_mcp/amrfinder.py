"""Optional wrapper around a locally installed AMRFinderPlus (``amrfinder``) binary."""

from __future__ import annotations

import asyncio
import csv
import io
import shutil
from pathlib import Path

TIMEOUT_SECONDS = 1800


def available() -> bool:
    return shutil.which("amrfinder") is not None


async def run(
    fasta_path: str, sequence_type: str, organism: str | None, threads: int = 4
) -> dict:
    if not available():
        raise RuntimeError(
            "AMRFinderPlus is not installed. Install it for free with "
            "`conda install -c bioconda ncbi-amrfinderplus` and run `amrfinder -u` once."
        )
    path = Path(fasta_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"FASTA file not found: {path}")

    flag = {"nucleotide": "-n", "protein": "-p"}[sequence_type]
    args = ["amrfinder", flag, str(path), "--plus", "--threads", str(threads)]
    if organism:
        args += ["-O", organism.replace(" ", "_")]

    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), TIMEOUT_SECONDS)
    except TimeoutError:
        proc.kill()
        raise RuntimeError(f"amrfinder timed out after {TIMEOUT_SECONDS}s") from None
    if proc.returncode != 0:
        raise RuntimeError(f"amrfinder failed: {stderr.decode(errors='replace')[-2000:]}")

    hits = list(csv.DictReader(io.StringIO(stdout.decode()), delimiter="\t"))
    return {"file": str(path), "organism": organism, "hit_count": len(hits), "hits": hits}
