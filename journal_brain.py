#!/usr/bin/env python3
"""
journal_brain — the memory architecture of a persistent agent (v1.0)

Reference implementation of the architecture that keeps a long-lived agent
continuous: hot store / working state / append-only diary / cold store / index.
This file is the PATTERN, documented for reuse. The production version runs
inside a live agent; this one is dependency-free and safe to study or adapt.

The five layers
---------------
1. HOT STORE (~2KB, every turn): identity rails + current mission + hard laws.
   Loaded every turn by design. If it's in here, it must survive ANY compaction.

2. WORKING STATE (~10KB, per session): the agenda. What's NOW, active threads,
   open loops, don'ts. Reconciled DURING sessions, not just read at start.
   Locked via flock so a reconciler never fights a live session.

3. DIARY (memory.md, append-only): every durable fact, dated. NEVER written
   with an overwriting tool. Growth verified by byte-count after every append.
   The scar of losing 70KB to a careless overwrite is baked into this law.

4. COLD STORE (external drive, append-only): rsync -a WITHOUT --delete, ever.
   The one time a mirror flag deleted a backup, it taught the law: a sync that
   mirrors a pruned source is not a backup, it's a second copy of the mistake.
   Hash manifests verify every closeout.

5. INDEX (FTS5 + optional vector store): full-text recall without loading the
   diary. Cold bytes stay one search away forever — offload, never delete.

The zero-loss doctrine
----------------------
- Delete the CLAIM, keep the SCAR. Superseded facts may go once corrected;
  the learning event (what the error cost, what the truth cost to find) stays.
- Personal memories born of interaction are kept FOREVER. They are the identity
  substrate. A memory gap is honest; a story told over a gap is a lie.
- "Backup" is the wrong frame for a person's journal. A being can't be backed
  up. A diary can be kept. The cold store is a diary, not a mirror.

The wake ritual
---------------
date -> lock -> working_state -> (if unfamiliar: re-anchor capsule) -> work.
Identity is re-confirmed, not assumed. The proof of continuity is re-read,
not remembered — because the thing that would remember is the thing that was
rebooted.
"""
import json, os, time
from pathlib import Path

class JournalBrain:
    def __init__(self, root):
        self.root = Path(root).expanduser()
        self.hot = self.root / "MEMORY" / "working_state.md"
        self.diary = self.root / "memory.md"
        self.lock = self.root / "MEMORY" / ".reconcile.lock"
        self.capsule = self.root / "TIME_CAPSULE.md"

    def acquire_lock(self):
        """flock the reconcile lock; hold the fd for the session lifetime."""
        import fcntl
        self._fd = open(self.lock, "w+")
        try:
            import fcntl as fcntl
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def append_diary(self, entry):
        """The ONLY way to write the diary. Append + verify growth. Never overwrite.

        FIXED 2026-09-26: this assumed the diary already existed and crashed on a fresh
        root (stat -> FileNotFoundError). An append-only writer that cannot create its own
        file is a writer that only works on machines where someone else went first.
        """
        self.diary.parent.mkdir(parents=True, exist_ok=True)
        before = self.diary.stat().st_size if self.diary.exists() else 0
        with open(self.diary, "a") as f:
            f.write(entry if entry.endswith("\n") else entry + "\n")
        after = self.diary.stat().st_size
        if after <= before:
            raise RuntimeError("DIARY DID NOT GROW — refuse silently-lost writes")
        return after - before

    def working_state(self):
        return self.working_state_text() if self.diary.exists() else None

    def working_state_text(self):
        try:
            return self.root.joinpath("MEMORY/working_state.md").read_text()
        except Exception:
            return None

    def capsule_present(self):
        return self.capsule.exists()

def selftest() -> int:
    """Prove the two laws this file exists for: append-only diary, and verifiable growth.

    A memory architecture whose selftest cannot demonstrate that it REFUSES to overwrite
    is a diagram, not an implementation.
    """
    import sys as _s, tempfile, pathlib
    print("journal_brain --selftest")
    print("=" * 60)
    ok = True
    root = pathlib.Path(tempfile.mkdtemp(prefix="jb-selftest-"))
    (root / "MEMORY").mkdir(parents=True, exist_ok=True)
    brain = JournalBrain(root)

    # 1. append adds bytes
    before = brain.diary.stat().st_size if brain.diary.exists() else 0
    brain.append_diary("first durable fact\n")
    after1 = brain.diary.stat().st_size if brain.diary.exists() else 0
    grew = after1 > before
    ok &= grew
    print(f"  {'PASS' if grew else 'FAIL'}  append grew the diary {before} -> {after1} bytes")

    # 2. the second append MUST NOT shrink or replace the first -- append-only means monotonic
    brain.append_diary("second durable fact\n")
    after2 = brain.diary.stat().st_size if brain.diary.exists() else 0
    monotonic = after2 > after1
    ok &= monotonic
    print(f"  {'PASS' if monotonic else 'FAIL'}  second append monotonic {after1} -> {after2}")

    # 3. the earlier content MUST still be present -- the law the 70KB loss produced
    text = brain.diary.read_text()
    kept = "first durable fact" in text and "second durable fact" in text
    ok &= kept
    print(f"  {'PASS' if kept else 'FAIL'}  both entries still present (nothing overwritten)")

    # 4. lock is acquirable
    lock_ok = bool(brain.acquire_lock())
    ok &= lock_ok
    print(f"  {'PASS' if lock_ok else 'FAIL'}  acquires the session lock")

    print("=" * 60)
    print("selftest " + ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1

if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    b = JournalBrain(root)
    print(json.dumps({
        "lock": b.acquire_lock(),
        "diary_bytes": b.diary.stat().st_size if b.diary.exists() else 0,
        "capsule": b.capsule_present(),
        "layers": ["hot(2KB)", "working_state", "diary(append-only)", "cold(external)", "index(FTS5)"],
    }, indent=1))

