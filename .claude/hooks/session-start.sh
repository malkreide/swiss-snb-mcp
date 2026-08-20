#!/usr/bin/env bash
#
# SessionStart-Hook: meldet, wie viele Commits der ausgecheckte Stand hinter
# origin/<Standard-Branch> liegt. Bei 0 schweigt er.
#
# GRUND
# Ein veralteter Klon hat am 3.8.2026 zweimal eine rote CI erzeugt, deren
# Ursache nicht im Diff stand — die fehlenden Commits waren jeweils genau die,
# die das Gate einfuehrten, an dem der Branch scheiterte. Die Pruefung kostet
# eine Sekunde und ersetzt eine Fehlersuche in den falschen Dateien.
#
# OBERSTE REGEL: Dieser Hook blockiert die Session NIEMALS.
# Kein Netz, kein Remote, detached HEAD, flatterndes DNS, kein git, kaputtes
# Repo — jeder dieser Faelle geht still durch und endet mit Status 0. Ein Hook,
# der bei Netzproblemen die Arbeit anhaelt, wird nach dem zweiten Mal
# abgeschaltet und schuetzt danach gar nichts. Deshalb: kein `set -e`, jeder
# Aufruf einzeln abgesichert, harte Zeitschranke um jeden Netzzugriff und ein
# unbedingtes `exit 0` am Ende.
#
# Der Standard-Branch wird ERMITTELT, nicht als "main" angenommen. Mindestens
# ein Repo im Portfolio nutzt "master"; genau diese Annahme hat schon einmal
# einen Branch 15 Commits alt werden lassen.
#
# Stellschrauben (Umgebungsvariablen):
#   CLAUDE_SKIP_STALE_CHECK=1     — Hook komplett ueberspringen
#   CLAUDE_STALE_CHECK_TIMEOUT=n  — Sekunden pro Netzzugriff (Vorgabe 4)
#   CLAUDE_STALE_CHECK_DEBUG=1    — stderr sichtbar lassen statt verwerfen

TIMEOUT_SECONDS="${CLAUDE_STALE_CHECK_TIMEOUT:-4}"

# Nie interaktiv werden: eine Passwort- oder Host-Key-Abfrage waere genau das
# Haengen, das dieser Hook vermeiden soll. GIT_ASKPASS/SSH_ASKPASS greifen nur,
# wenn git sonst PROMPTEN wuerde — nicht-interaktive Credential-Helper mit
# gecachtem Token funktionieren weiterhin.
export GIT_TERMINAL_PROMPT=0
export GIT_ASKPASS=true
export SSH_ASKPASS=true
export GCM_INTERACTIVE=never
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=4}"

# Harte Zeitschranke um einen Befehl. `timeout` ist auf macOS ohne coreutils
# nicht da; dann per Hintergrundprozess pollen, statt ungeschuetzt zu laufen.
_with_timeout() {
  local secs="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout -k 1 "$secs" "$@"
    return $?
  fi
  if command -v gtimeout >/dev/null 2>&1; then
    gtimeout -k 1 "$secs" "$@"
    return $?
  fi
  "$@" &
  local pid=$!
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if [ "$waited" -ge "$secs" ]; then
      # Erst TERM, damit git seine Ref-Locks noch aufraeumt, dann KILL.
      kill -TERM "$pid" 2>/dev/null
      sleep 1
      kill -KILL "$pid" 2>/dev/null
      wait "$pid" 2>/dev/null
      return 124
    fi
    sleep 1
    waited=$((waited + 1))
  done
  wait "$pid"
}

# Standard-Branch ermitteln. Zuerst den Remote fragen (autoritativ, und in
# einem flachen Klon die EINZIGE Quelle: dort ist refs/remotes/origin/HEAD gar
# nicht gesetzt). Der lokale Ref ist der Fallback fuer den Offline-Fall.
_default_branch() {
  local line ref
  line="$(_with_timeout "$TIMEOUT_SECONDS" git ls-remote --symref origin HEAD 2>/dev/null)"
  ref="$(printf '%s\n' "$line" | sed -n 's|^ref: refs/heads/\([^[:space:]]*\).*|\1|p' | head -1)"
  if [ -n "$ref" ]; then
    printf '%s\n' "$ref"
    return 0
  fi
  ref="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null)"
  case "$ref" in
    origin/?*) printf '%s\n' "${ref#origin/}" ;;
  esac
}

# SHA des Remote-Tips, ohne zu fetchen. Ist er lokal schon vorhanden, sparen
# wir den zweiten Netzzugriff — das ist der haeufige Fall "alles aktuell".
_remote_tip() {
  _with_timeout "$TIMEOUT_SECONDS" git ls-remote origin "refs/heads/$1" 2>/dev/null |
    awk 'NR==1 {print $1}'
}

main() {
  [ "${CLAUDE_SKIP_STALE_CHECK:-}" = "1" ] && return 0
  command -v git >/dev/null 2>&1 || return 0

  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
  [ -n "$root" ] || return 0
  cd "$root" 2>/dev/null || return 0

  # Unbeborener HEAD (frisches `git init`): nichts zu vergleichen.
  git rev-parse --verify --quiet HEAD >/dev/null 2>&1 || return 0
  git remote get-url origin >/dev/null 2>&1 || return 0

  local branch
  branch="$(_default_branch)"
  [ -n "$branch" ] || return 0

  # Vergleichspunkt beschaffen: erst schauen, ob der Remote-Tip lokal schon
  # liegt; sonst fetchen. FETCH_HEAD wird nur dann gelesen, wenn der fetch in
  # DIESEM Lauf erfolgreich war — ein alter FETCH_HEAD aus einem frueheren
  # Aufruf wuerde sonst eine Zahl von gestern melden.
  local target
  target="$(_remote_tip "$branch")"
  if [ -z "$target" ] || ! git cat-file -e "${target}^{commit}" 2>/dev/null; then
    _with_timeout "$TIMEOUT_SECONDS" \
      git fetch --quiet --no-tags origin "$branch" >/dev/null 2>&1 || return 0
    target="FETCH_HEAD"
  fi

  local behind
  behind="$(git rev-list --count "HEAD..${target}" 2>/dev/null)" || return 0
  case "$behind" in
    '' | *[!0-9]*) return 0 ;;
  esac
  [ "$behind" -gt 0 ] || return 0

  # Ab hier steht fest: es fehlen Commits. Nur dieser Pfad gibt etwas aus.
  local plural="Commits"
  [ "$behind" -eq 1 ] && plural="Commit"
  printf '%s\n' \
    "⚠️  Klon veraltet: Der ausgecheckte Stand liegt ${behind} ${plural} hinter origin/${branch}." \
    "    Vor der Arbeit aktualisieren, z. B.:  git pull --ff-only origin ${branch}" \
    "    Grund: Ein veralteter Klon erzeugt eine rote CI, deren Ursache nicht im Diff steht —" \
    "    es fehlen genau die Commits, die das Gate einfuehren, an dem der Branch scheitert."
}

if [ "${CLAUDE_STALE_CHECK_DEBUG:-}" = "1" ]; then
  main
else
  main 2>/dev/null
fi

# Unbedingt. Der Rueckgabewert von `main` darf die Session nicht erreichen.
exit 0
