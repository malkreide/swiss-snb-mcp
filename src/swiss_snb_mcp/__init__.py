from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    # Aus den installierten Paket-Metadaten, die aus pyproject.toml erzeugt
    # werden. Ein von Hand gepflegtes Literal laeuft frueher oder spaeter
    # von der Paketversion weg — genau das ist portfolioweit passiert.
    __version__ = _distribution_version("swiss-snb-mcp")
except PackageNotFoundError:
    # Quellbaum ohne Installation. Bewusst keine plausibel aussehende Nummer:
    # ein erkennbar unfertiger Marker ist besser als eine falsche Version.
    __version__ = "0.0.0+source"
