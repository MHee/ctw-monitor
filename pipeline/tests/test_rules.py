"""Guards for the hard rules in CLAUDE.md that can be checked mechanically."""
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_no_data_files_tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return  # not a git checkout yet
    bad = [f for f in out if f.startswith("web/public/data/") or f.endswith((".parquet", ".nc"))]
    assert not bad, bad


def test_no_kelvin_wave_in_ui_strings():
    """Rule 1: the UI says coastal-trapped wave; 'Kelvin wave' only inside quotes."""
    for f in (REPO / "web" / "src").rglob("*.vue"):
        txt = f.read_text(encoding="utf-8")
        for line in txt.splitlines():
            if "Kelvin wave" in line:
                assert "\u201c" in line or '"Kelvin wave"' in line or "&ldquo;" in line, f"{f.name}: {line.strip()}"
