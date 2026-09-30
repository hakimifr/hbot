import datetime
import inspect
import logging
import queue
import threading
from dataclasses import dataclass
from logging import LogRecord
from logging.handlers import QueueHandler

from rich.console import Console
from rich.markup import escape
from rich.text import Text

lg: logging.Logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO)

QUEUE_MAXSIZE = 10_000


@dataclass(frozen=True)
class CalleeInfo:
    module_name: str
    fn_name: str
    file: str
    lineno: int


class DroppingQueueHandler(QueueHandler):
    """QueueHandler that counts and drops records instead of erroring when the queue is full."""

    def __init__(self, q: queue.Queue[LogRecord | None]) -> None:
        super().__init__(q)
        self.dropped: int = 0

    def emit(self, record: LogRecord) -> None:
        try:
            self.enqueue(self.prepare(record))
        except queue.Full:
            self.dropped += 1


class Logger:
    def __init__(self) -> None:
        self.thread = threading.Thread(target=self.run_loop, daemon=True)
        self.queue: queue.Queue[LogRecord | None] = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self.queue_handler = DroppingQueueHandler(self.queue)
        self.console = Console(force_terminal=True, soft_wrap=True)

        self.thread.start()
        lg.info("logger thread started")

        self.level_colour: dict[int, str] = {
            logging.DEBUG: "blue",
            logging.INFO: "green",
            logging.WARNING: "yellow",
            logging.ERROR: "magenta",
            logging.FATAL: "brred",
        }

    def get_callee_info(self) -> CalleeInfo:
        frame_info: inspect.FrameInfo = inspect.stack()[2]

        module = inspect.getmodule(frame_info.frame)
        module_name = module.__name__ if module else "__main__"

        function_name = frame_info.function
        file = frame_info.filename
        lineno = frame_info.lineno

        return CalleeInfo(
            module_name=module_name,
            fn_name=function_name,
            file=file,
            lineno=lineno,
        )

    def report_dropped(self) -> None:
        """Log (once per batch) how many records were dropped because the queue was full."""
        dropped = self.queue_handler.dropped
        if not dropped:
            return

        self.queue_handler.dropped = 0
        record = LogRecord(
            name=lg.name,
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg="dropped %d log records because the queue was full",
            args=(dropped,),
            exc_info=None,
        )
        try:
            self.queue_handler.enqueue(record)
        except queue.Full:
            # The warning itself was dropped; keep it counted for the next report.
            self.queue_handler.dropped += 1

    def run_loop(self) -> None:
        with open("bot.log", "a+") as f:
            while True:
                log_data = self.queue.get()

                try:
                    if log_data is None:
                        break

                    if isinstance(log_data, LogRecord):
                        level_colour = self.level_colour[log_data.levelno]
                        time = datetime.datetime.now(tz=datetime.UTC)
                        prefix = (
                            f"[{time}] [{level_colour}]{log_data.levelname}[/{level_colour}] "
                            f"[grey]<{log_data.filename}>[/grey] {log_data.name}: "
                        )
                        msg = (prefix + escape(log_data.getMessage())).replace("\n", f"\n{prefix}")
                        self.console.print(msg)
                        f.write(Text.from_markup(msg).plain + "\n")
                        f.flush()
                finally:
                    self.queue.task_done()
                    self.report_dropped()

    def setup_redirect(self) -> None:
        root = logging.getLogger()

        for h in root.handlers:
            root.removeHandler(h)

        root.addHandler(self.queue_handler)


logger = Logger()
logger.setup_redirect()


# ruff: disable[N802]
def getLogger(*args) -> Logger:
    return logger
