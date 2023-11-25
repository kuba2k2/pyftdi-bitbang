#  Copyright (c) Kuba Szczodrzyński 2023-11-20.

from abc import ABC
from functools import partial
from itertools import chain
from time import time
from typing import Any, Iterable, Optional, Union

from pyftdi.gpio import GpioAsyncController, GpioBaseController, GpioSyncController
from pyftdi.spi import SpiController, SpiIOError, SpiPort
from usb.core import Device as UsbDevice

from .base import BitBangBase

SCK = 0
MOSI = 1
MISO = 2
CS0 = 3


class BitBangSpiController(BitBangBase, SpiController, ABC):
    def __init__(
        self,
        gpio: GpioBaseController,
        sck: int = SCK,
        mosi: int = MOSI,
        miso: int = MISO,
        cs: int = CS0,
        cs_count: int = 1,
        turbo: bool = True,
    ):
        SpiController.__init__(self, cs_count, turbo)
        super().__init__(gpio)
        self.SCK_BIT = 1 << sck
        self.DO_BIT = 1 << mosi
        self.DI_BIT = 1 << miso
        self.CS_BIT = 1 << cs
        self.SPI_BITS = self.DI_BIT | self.DO_BIT | self.SCK_BIT

    @property
    def _bus_mask(self) -> int:
        return self._spi_mask

    @property
    def _bus_dir(self) -> int:
        return self._spi_dir

    def configure(
        self,
        url: Union[str, UsbDevice],
        **kwargs: Any,
    ) -> None:
        if "cs_count" in kwargs:
            self._cs_count = int(kwargs["cs_count"])
            del kwargs["cs_count"]
        if not 1 <= self._cs_count <= 5:
            raise ValueError("Unsupported CS line count: %d" % self._cs_count)
        if "direction" in kwargs:
            io_dir = int(kwargs["direction"])
            del kwargs["direction"]
        else:
            io_dir = 0
        if "initial" in kwargs:
            io_out = int(kwargs["initial"])
            del kwargs["initial"]
        else:
            io_out = 0

        with self._lock:
            if self._frequency > 0.0:
                raise SpiIOError("Already configured")
            self._cs_bits = ((self.CS_BIT << self._cs_count) - 1) & ~(self.CS_BIT - 1)
            self._spi_ports = [None] * self._cs_count
            self._spi_dir = self._cs_bits | self.DO_BIT | self.SCK_BIT
            self._spi_mask = self._cs_bits | self.SPI_BITS
            self._gpio_mask = (~self._spi_mask) & 0xFF
            self._gpio_dir = io_dir & self._gpio_mask

            kwargs["direction"] = self._spi_dir | self._gpio_dir
            kwargs["initial"] = self._cs_bits | (io_out & self._gpio_dir)
            self._port_val = kwargs["initial"] & (self._spi_dir | self._gpio_dir)
            self._gpio.configure(url, **kwargs)
            self._frequency = self._gpio.frequency

    def get_port(self, cs: int, freq: Optional[float] = None, mode: int = 0) -> SpiPort:
        # replace set_mode()
        port = super().get_port(cs, freq, mode)
        port.set_mode = partial(BitBangSpiPort.set_mode, port)
        port.set_mode(port.mode)
        return port

    def set_gpio_direction(self, pins: int, direction: int) -> None:
        with self._lock:
            super()._set_gpio_direction(8, pins, direction)
            if not self._gpio.is_connected:
                return
            self._gpio.set_direction(
                pins=self._spi_mask | self._gpio_mask,
                direction=self._spi_dir | self._gpio_dir,
            )

    def exchange(
        self,
        frequency: float,
        out: Union[bytes, bytearray, Iterable[int]],
        readlen: int,
        cs_prolog: Optional[bytes] = None,
        cs_epilog: Optional[bytes] = None,
        cpol: bool = False,
        cpha: bool = False,
        duplex: bool = False,
        droptail: int = 0,
    ) -> bytes:
        # TODO support setting frequency here
        if cpol or cpha:
            raise NotImplementedError("CPOL/CPHA is not implemented yet")
        if droptail:
            raise NotImplementedError("'droptail' is not implemented yet")

        for value in cs_prolog:
            self._write_bus(value)

        is_async = isinstance(self._gpio, GpioAsyncController)
        is_sync = isinstance(self._gpio, GpioSyncController)

        if is_sync and not duplex:
            # add space for received data in half-duplex & sync-mode
            out_padding = b"\x00" * readlen
        elif duplex and readlen > len(out):
            # reading more than sending, add padding in full-duplex mode
            out_padding = b"\x00" * (readlen - len(out))
        else:
            # no padding necessary
            out_padding = b""

        recv_data = bytearray()
        for byte in chain(out, out_padding):
            recv_byte = 0
            for bit in range(8):
                if byte & (1 << (7 - bit)):
                    value = (self._port_val & ~self.SCK_BIT) | self.DO_BIT
                else:
                    value = (self._port_val & ~self.SCK_BIT) & ~self.DO_BIT
                self._write_bus(value)
                self._write_high(self.SCK_BIT)
                if duplex and is_async and self._read_pin(self.DI_BIT):
                    recv_byte |= 1 << (7 - bit)
            if duplex and is_async:
                recv_data.append(recv_byte)

        # perform sync-mode exchange
        if is_sync:
            self._exchange_bus()
            for _ in cs_prolog:
                # skip /CS input values
                self._read_pin(0)
            if not duplex:
                # skip 'out'-data input values
                for _ in range(len(out) * 8 * 2):
                    self._read_pin(0)

        if is_async:
            if duplex:
                # full-duplex & async, data already received
                recv_data = recv_data[0:readlen]
            else:
                # half-duplex & async, clock-in data
                time()
                assert len(recv_data) == 0
                for _ in range(readlen):
                    recv_byte = 0
                    for bit in range(8):
                        self._write_low(self.SCK_BIT)
                        self._write_high(self.SCK_BIT)
                        if self._read_pin(self.DI_BIT):
                            recv_byte |= 1 << (7 - bit)
                    recv_data.append(recv_byte)
                time()

        elif is_sync:
            # half-/full-duplex & sync, data received in exchange
            assert len(recv_data) == 0
            for _ in range(readlen):
                recv_byte = 0
                for bit in range(8):
                    self._read_pin(0)  # skip SCK toggle
                    if self._read_pin(self.DI_BIT):
                        recv_byte |= 1 << (7 - bit)
                recv_data.append(recv_byte)
            if duplex:
                recv_data = recv_data[0:readlen]

        for value in cs_epilog[:32]:
            self._write_bus(value)
        # send sync-mode exchange, ignore results
        self._exchange_bus()

        assert len(recv_data) == readlen
        return recv_data


class BitBangSpiPort(SpiPort):
    def set_mode(self, mode: int, cs_hold: Optional[int] = None) -> None:
        SpiPort.set_mode(self, mode, cs_hold)
        # make set_mode() respect the controller's ###_BIT props
        cs_clock = 0xFF & ~(
            (int(not self._cpol) and self._controller.SCK_BIT) | self._controller.DO_BIT
        )
        cs_select = 0xFF & ~(
            (self._controller.CS_BIT << self._cs)
            | (int(not self._cpol) and self._controller.SCK_BIT)
            | self._controller.DO_BIT
        )
        self._cs_prolog = bytes([cs_clock, cs_select])
        self._cs_epilog = bytes([cs_select] + [cs_clock] * int(self._cs_hold))
