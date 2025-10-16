from .logger import get_logger
from .server.cli import main


if __name__ == "__main__":  # pragma: no cover - entry point
    get_logger(__name__).debug("FeatherFlap module executed as a script")
    main()
