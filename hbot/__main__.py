import uvloop

from hbot.core import coloured_logging_setup  # noqa: F401
from hbot.core.main import main

if __name__ == "__main__":
    uvloop.run(main())
