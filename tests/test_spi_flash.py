#  Copyright (c) Kuba Szczodrzyński 2023-11-25.

from os import environ

import pytest
from pyftdi.gpio import GpioAsyncController, GpioBaseController, GpioSyncController

from pyftdibb.spi import BitBangSpiController


@pytest.mark.parametrize(
    "mode,frequency",
    [
        ("async", 57600),
        ("async", 115200),
        ("async", 230400),
        ("async", 460800),
        ("async", 921600),
        ("sync", 500),
        ("sync", 1_000),
        ("sync", 5_000),
        ("sync", 10_000),
        ("sync", 100_000),
        ("sync", 500_000),
        ("sync", 1_000_000),
        ("sync", 1_500_000),
        ("sync", 2_000_000),
    ],
)
@pytest.mark.parametrize("duplex", [False, True])
class TestSpiFlash:
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

    def test_bit_bang_modes(self, duplex: bool) -> None:
        port = self.spi.get_port(cs=0)
        for _ in range(5):
            if not duplex:
                flash_id = port.exchange(b"\x9F", readlen=3, duplex=False)
            else:
                flash_id = port.exchange(b"\x9F", readlen=4, duplex=True)
                flash_id = flash_id[1:]
            assert flash_id.hex() == self.flash_id.hex(), (
                "Should be %s" % self.flash_id.hex()
            )
