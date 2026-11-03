import sys

from scripts.cli import cli


def main():
    # Chamado pelo shim do biber que o engine Tectonic põe no PATH (ver
    # scripts/bibcache.py): fora do argparse pra não depender das flags.
    if len(sys.argv) > 1 and sys.argv[1] == "--biber-cache":
        from scripts.bibcache import main as biber_cache

        sys.exit(biber_cache(sys.argv[2:]))
    cli()

if __name__ == "__main__":
    main()
