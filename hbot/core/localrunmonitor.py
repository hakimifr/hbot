import logging
import re
import subprocess
import time
from threading import Thread

from pyrogram.client import Client

from hbot import LOCALRUN

logger = logging.getLogger(__name__)


class LocalRunMonitor:
    def __init__(self, app: Client):
        self.thread = Thread(target=self.main_loop, daemon=True)
        self.app = app

    def start(self) -> None:
        if LOCALRUN:
            logger.info("bot is running locally. starting LocalRunMonitor")
            self.thread.start()

    # ruff: disable[S603,S607]
    def get_battery_percentage(self) -> int | None:
        try:
            # Find the battery device path
            output = subprocess.check_output(["upower", "-e"], text=True)
            battery = next((line for line in output.splitlines() if "battery" in line), None)
            if not battery:
                return None

            # Query that device
            info = subprocess.check_output(["upower", "-i", battery], text=True)
            match = re.search(r"percentage:\s+(\d+)%", info)
            return int(match.group(1)) if match else None

        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def main_loop(self) -> None:
        while True:
            time.sleep(60 * 5)
            logger.debug("polling device battery level")
            battery = self.get_battery_percentage()
            if battery is None:
                logger.error("could not get device's battery percentage")
                continue

            if battery < 30:
                logger.info("sending low battery message")
                self.app.send_message(-1001155763792, "laptop battery level is low!")
            else:
                logger.info("battery is above threshold")
