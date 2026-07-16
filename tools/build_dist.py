"""Build the shippable single-file collector artifacts into dist/.

Customers must be able to audit exactly one file, so the delta module is
inlined into each collector and a .sha256 checksum file is written next to
each artifact (the script also prints its own hash at run time — the two
must match what we publish).
"""

from __future__ import annotations

import hashlib
import py_compile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# the exact runtime-import block both collectors use for --delta-of;
# in the dist artifact apply_delta is defined at module level instead
DELTA_IMPORT_BLOCK = """\
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            from delta import apply_delta
        except ImportError:
            print("error: --delta-of requires delta.py next to this script", file=sys.stderr)
            return 1
"""

MAIN_GUARD = 'if __name__ == "__main__":'


def build(name: str) -> None:
    src = (REPO / "collector" / name).read_text(encoding="utf-8")
    delta_src = (REPO / "collector" / "delta.py").read_text(encoding="utf-8")
    # __future__ imports are only legal at the top of a file
    delta_src = delta_src.replace("from __future__ import annotations\n", "")

    assert DELTA_IMPORT_BLOCK in src, f"delta import block not found in {name}"
    assert MAIN_GUARD in src
    src = src.replace(DELTA_IMPORT_BLOCK, "")
    inlined = (
        "\n# ===== inlined from collector/delta.py by tools/build_dist.py =====\n"
        f"{delta_src}"
        "# ===== end of inlined delta.py =====\n\n\n"
    )
    src = src.replace(MAIN_GUARD, inlined + MAIN_GUARD)

    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / name
    out.write_text(src, encoding="utf-8")
    py_compile.compile(str(out), doraise=True)  # artifact must at least parse

    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    (dist / f"{name}.sha256").write_text(f"{sha}  {name}\n")
    print(f"dist/{name}  sha256={sha}")


if __name__ == "__main__":
    build("pg_collect.py")
    build("mysql_collect.py")
