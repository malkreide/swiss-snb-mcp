"""SessionStart-Hook: meldet Rueckstand, blockiert nie.

Die Zusicherungen des Hooks sind Verhaltens-, keine Code-Aussagen — deshalb
faehrt dieser Test das Skript als Prozess gegen echte Wegwerf-Repos statt
seine Innereien nachzubauen. Eine handgeschriebene Attrappe von `git fetch`
koennte die Aussage "haengt nie" nicht widerlegen; ein echtes, absichtlich
haengendes `git` kann es.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "session-start.sh"
# Absolut aufloesen: `test_kein_git_im_pfad` leert den PATH, und ein relativ
# gesuchtes `bash` waere dann genauso weg wie das `git`, um das es geht.
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or BASH is None,
    reason="git oder bash nicht verfuegbar",
)


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    out = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _commit(repo: Path, message: str) -> None:
    (repo / "f.txt").write_text(f"{message}\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", message)


def _run(cwd: Path, **env_extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **env_extra}
    env.pop("CLAUDE_SKIP_STALE_CHECK", None)
    env.update(env_extra)
    assert BASH is not None
    return subprocess.run(
        [BASH, str(HOOK)], cwd=cwd, env=env, capture_output=True, text=True
    )


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    """Ein Bare-Remote mit einem Commit auf dem Branch `main`."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _commit(work, "c1")
    bare = tmp_path / "origin.git"
    _git(work, "clone", "-q", "--bare", str(work), str(bare))
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    return bare


@pytest.fixture
def clone(tmp_path: Path, upstream: Path) -> Path:
    dest = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(upstream), str(dest))
    return dest


def _advance(upstream: Path, tmp_path: Path, n: int, branch: str = "main") -> None:
    """Schiebt `n` neue Commits auf den Remote-Branch."""
    pusher = tmp_path / f"pusher-{branch}"
    if not pusher.exists():
        _git(tmp_path, "clone", "-q", "-b", branch, str(upstream), str(pusher))
    for i in range(n):
        _commit(pusher, f"neu-{branch}-{i}")
    _git(pusher, "push", "-q", "origin", branch)


class TestMeldetRueckstand:
    def test_schweigt_wenn_aktuell(self, clone: Path):
        got = _run(clone)
        assert got.returncode == 0
        assert got.stdout == ""

    @pytest.mark.parametrize("n", [1, 3])
    def test_meldet_exakte_anzahl(self, clone: Path, upstream: Path, tmp_path, n: int):
        _advance(upstream, tmp_path, n)
        got = _run(clone)
        assert got.returncode == 0
        assert f"{n} Commit" in got.stdout
        assert "origin/main" in got.stdout

    def test_singular_bei_genau_einem(self, clone: Path, upstream: Path, tmp_path):
        _advance(upstream, tmp_path, 1)
        assert "1 Commit hinter" in _run(clone).stdout

    def test_plural_ab_zwei(self, clone: Path, upstream: Path, tmp_path):
        _advance(upstream, tmp_path, 2)
        assert "2 Commits hinter" in _run(clone).stdout

    def test_eigene_commits_zaehlen_nicht_als_rueckstand(self, clone: Path):
        """Voraus zu sein ist kein Rueckstand — sonst meldet der Hook bei
        jedem lokalen Commit."""
        _commit(clone, "lokal")
        got = _run(clone)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_detached_head_wird_gezaehlt(self, clone: Path, upstream: Path, tmp_path):
        _advance(upstream, tmp_path, 2)
        _git(clone, "checkout", "-q", "--detach", "HEAD")
        got = _run(clone)
        assert got.returncode == 0
        assert "2 Commits hinter" in got.stdout


class TestStandardBranchWirdErmittelt:
    """Nicht `main` annehmen: drei Repos im Portfolio heissen ihn `master`."""

    def test_master_statt_main(self, tmp_path: Path):
        work = tmp_path / "w"
        work.mkdir()
        _git(work, "init", "-q", "-b", "master")
        _commit(work, "c1")
        bare = tmp_path / "o.git"
        _git(work, "clone", "-q", "--bare", str(work), str(bare))
        _git(bare, "symbolic-ref", "HEAD", "refs/heads/master")
        dest = tmp_path / "c"
        _git(tmp_path, "clone", "-q", str(bare), str(dest))
        _advance(bare, tmp_path, 2, branch="master")

        got = _run(dest)
        assert got.returncode == 0
        assert "2 Commits hinter origin/master" in got.stdout

    def test_flacher_klon_ohne_origin_head_ref(self, clone: Path, upstream: Path):
        """In einem flachen Klon ist refs/remotes/origin/HEAD nicht gesetzt —
        genau so checkt Claude Code on the web aus. Der Remote muss also
        gefragt werden, ein rein lokaler Ansatz waere dort wirkungslos."""
        _git(clone, "update-ref", "-d", "refs/remotes/origin/HEAD")
        assert "main" not in _git(clone, "branch", "-r")  # nur origin/main bleibt
        got = _run(clone)
        assert got.returncode == 0


class TestBlockiertNie:
    """Jeder Stoerfall geht still durch und endet mit Status 0."""

    def test_kein_git_repo(self, tmp_path: Path):
        plain = tmp_path / "plain"
        plain.mkdir()
        got = _run(plain)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_kein_remote(self, tmp_path: Path):
        solo = tmp_path / "solo"
        solo.mkdir()
        _git(solo, "init", "-q", "-b", "main")
        _commit(solo, "c1")
        got = _run(solo)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_unbeborener_head(self, tmp_path: Path):
        fresh = tmp_path / "fresh"
        fresh.mkdir()
        _git(fresh, "init", "-q", "-b", "main")
        _git(fresh, "remote", "add", "origin", str(tmp_path / "nirgendwo.git"))
        got = _run(fresh)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_unerreichbarer_remote(self, clone: Path, tmp_path: Path):
        _git(clone, "remote", "set-url", "origin", str(tmp_path / "weg.git"))
        got = _run(clone)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_kein_git_im_pfad(self, clone: Path, tmp_path: Path):
        leer = tmp_path / "leerer-pfad"
        leer.mkdir()
        got = _run(clone, PATH=str(leer))
        assert got.returncode == 0
        assert got.stdout == ""

    def test_status_0_auch_wenn_die_ausgabe_selbst_scheitert(
        self, clone: Path, upstream: Path, tmp_path
    ):
        """Das unbedingte `exit 0` am Skriptende, einzeln nachgewiesen.

        Ist stdout geschlossen, scheitert das `printf` — und der Rueckgabewert
        von `main` waere ungleich 0. Ohne das `exit 0` reicht der Hook genau
        diesen Fehler an die Session durch, ausgerechnet im Meldefall.
        """
        _advance(upstream, tmp_path, 2)
        assert BASH is not None
        got = subprocess.run(
            [BASH, "-c", 'exec "$0" "$1" >&-', BASH, str(HOOK)],
            cwd=clone,
            env={**os.environ},
            capture_output=True,
            text=True,
        )
        assert got.returncode == 0

    def test_skip_schalter(self, clone: Path, upstream: Path, tmp_path):
        _advance(upstream, tmp_path, 3)
        got = _run(clone, CLAUDE_SKIP_STALE_CHECK="1")
        assert got.returncode == 0
        assert got.stdout == ""


class TestZeitschranke:
    """Die Zusicherung ist «haengt nicht», und sie braucht echte Zeit.

    Eine Fake-Uhr, die nur beim Schlafen vorrueckt, koennte hier nichts
    widerlegen: gemessen wird die Wanduhr eines fremden Prozesses.
    """

    @staticmethod
    def _git_das_haengt(tmp_path: Path, unterbefehl: str) -> Path:
        echtes_git = shutil.which("git")
        assert echtes_git is not None
        shim_dir = tmp_path / f"shim-{unterbefehl}"
        shim_dir.mkdir()
        shim = shim_dir / "git"
        shim.write_text(
            "#!/bin/sh\n"
            'for a in "$@"; do\n'
            f'  if [ "$a" = "{unterbefehl}" ]; then sleep 120; exit 0; fi\n'
            "done\n"
            f'exec {echtes_git} "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
        return shim_dir

    @pytest.mark.parametrize("unterbefehl", ["ls-remote", "fetch"])
    def test_haengendes_git_wird_abgeraeumt(
        self, clone: Path, tmp_path: Path, unterbefehl: str
    ):
        shim_dir = self._git_das_haengt(tmp_path, unterbefehl)
        start = time.monotonic()
        got = _run(
            clone,
            PATH=f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
            CLAUDE_STALE_CHECK_TIMEOUT="2",
        )
        dauer = time.monotonic() - start

        assert got.returncode == 0
        assert got.stdout == ""
        # Grosszuegig gegen langsame Runner, aber weit unter den 120 s des
        # Shims: ohne Zeitschranke schluege das hier fehl.
        assert dauer < 30, f"Hook lief {dauer:.1f}s — Zeitschranke greift nicht"


class TestKeinAltesFetchHead:
    """FETCH_HEAD darf nur gelesen werden, wenn der fetch in DIESEM Lauf lief.

    Ein sauber scheiternder fetch leert FETCH_HEAD selbst — der gefaehrliche
    Fall ist der ABGERAEUMTE fetch: die Zeitschranke schiesst ihn ab, und der
    FETCH_HEAD des letzten erfolgreichen Laufs bleibt unversehrt liegen. Ohne
    die Absicherung meldet der Hook dann eine Zahl von gestern, die niemand
    nachvollziehen kann — schlimmer als keine Meldung.
    """

    def test_sauber_gescheiterter_fetch_meldet_nichts(
        self, clone: Path, upstream: Path, tmp_path: Path
    ):
        _advance(upstream, tmp_path, 4)
        _git(clone, "fetch", "-q", "origin", "main")  # legt FETCH_HEAD an
        assert (clone / ".git" / "FETCH_HEAD").read_text(encoding="utf-8").strip()
        _git(clone, "remote", "set-url", "origin", str(tmp_path / "weg.git"))

        got = _run(clone)
        assert got.returncode == 0
        assert got.stdout == ""

    def test_abgeraeumter_fetch_meldet_nichts_aus_altem_fetch_head(
        self, clone: Path, upstream: Path, tmp_path: Path
    ):
        _advance(upstream, tmp_path, 4)
        _git(clone, "fetch", "-q", "origin", "main")
        alt = (clone / ".git" / "FETCH_HEAD").read_text(encoding="utf-8")
        assert alt.strip(), "Vorbedingung: FETCH_HEAD ist gefuellt"

        # `ls-remote` scheitert (kein Remote-Tip), `fetch` haengt und wird von
        # der Zeitschranke abgeschossen — FETCH_HEAD ueberlebt dabei.
        echtes_git = shutil.which("git")
        assert echtes_git is not None
        shim_dir = tmp_path / "shim-stale"
        shim_dir.mkdir()
        shim = shim_dir / "git"
        shim.write_text(
            "#!/bin/sh\n"
            'for a in "$@"; do\n'
            '  [ "$a" = "ls-remote" ] && exit 1\n'
            '  [ "$a" = "fetch" ] && { sleep 120; exit 0; }\n'
            "done\n"
            f'exec {echtes_git} "$@"\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)

        got = _run(
            clone,
            PATH=f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
            CLAUDE_STALE_CHECK_TIMEOUT="2",
        )

        assert got.returncode == 0
        assert (clone / ".git" / "FETCH_HEAD").read_text(encoding="utf-8") == alt, (
            "Vorbedingung: der abgeraeumte fetch hat FETCH_HEAD nicht angetastet"
        )
        assert got.stdout == "", "Zahl aus einem FETCH_HEAD von frueher gemeldet"
