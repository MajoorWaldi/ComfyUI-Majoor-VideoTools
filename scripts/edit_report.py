"""The report of a finished edit: contact sheet, first frame, black stretches, cuts against the music, loudness. No model and no GPU.

    python scripts/edit_report.py <project id or folder> --video <the edit .mp4> [--out folder]

It writes edit_report.json and sheet-N.png to <project>/exports (or --out)."""
import argparse
import json
import sys
import types
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
package = types.ModuleType("majoor_videotools")  # the report is plain Python: the pack is read as a package without starting ComfyUI
package.__path__ = [str(PACK)]
sys.modules.setdefault("majoor_videotools", package)
from majoor_videotools.core.edit_report import edit_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="a project id (p_...) under the output folder, or the folder of a project")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--root", type=Path, default=Path("D:/____COMFY_OUTPUTS/MajoorVideoTools"), help="the folder of the projects")
    args = parser.parse_args()
    folder = Path(args.project) if Path(args.project).is_dir() else args.root / args.project
    report = edit_report(folder, args.video, args.out)
    sync = report["sync"] or {}
    print(f"first frame {'ok' if report['first_frame']['ok'] else 'EMPTY'} | black stretches {len(report['black'])} | loudness {report['loudness']['integrated_lufs']} LUFS, true peak {report['loudness']['true_peak_dbtp']} dBTP")
    print(f"cuts {len(report['cuts'])} | within 50 ms of an attack {sync.get('within_50ms')} | median {sync.get('median_ms')} ms | sheets {', '.join(report['sheets'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
