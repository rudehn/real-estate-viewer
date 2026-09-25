import logging
import sys


def get_logger(name: str) -> logging.Logger:
    # Module loggers carry no handlers of their own: records propagate to the
    # root handler set up once by configure_logging() at each entry point
    # (main.py, cli.py). A handler here too would print every line twice.
    return logging.getLogger(name)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
