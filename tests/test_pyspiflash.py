#  Copyright (c) Kuba Szczodrzyński 2023-11-25.

from os import environ

import pytest
from pyftdi.gpio import GpioAsyncController, GpioBaseController, GpioSyncController
from spiflash.serialflash import SerialFlashManager

from pyftdibb.spi import BitBangSpiController


@pytest.mark.parametrize("mode,frequency", [("async", 115200), ("sync", 500_000)])
class TestPySpiFlash:
    ftdi_url: str
    flash_id: bytes

    gpio: GpioBaseController
    spi: BitBangSpiController

    @pytest.fixture(scope="function", autouse=True)
    def setup_and_teardown(self, mode: str, frequency: int) -> None:
        self.ftdi_url = environ.get("FTDI_DEVICE", "ftdi:///1")
        self.flash_id = bytes.fromhex(environ.get("FLASH_ID", "ef 40 18"))
        if mode == "async":
            self.gpio = GpioAsyncController()
        else:
            self.gpio = GpioSyncController()
        self.spi = BitBangSpiController(gpio=self.gpio)
        self.spi.configure(self.ftdi_url, frequency=frequency)
        yield
        self.spi.close()

    def test_pyspiflash_id(self) -> None:
        port = self.spi.get_port(cs=0)
        for _ in range(5):
            flash_id = SerialFlashManager.read_jedec_id(port)
            assert flash_id.hex() == self.flash_id.hex(), (
                "Should be %s" % self.flash_id.hex()
            )
