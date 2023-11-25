#  Copyright (c) Kuba Szczodrzyński 2023-11-21.

from threading import Lock

from pyftdi.gpio import GpioAsyncController, GpioBaseController, GpioSyncController


class BitBangBase:
    _lock: Lock
    _frequency: float
    _gpio: GpioBaseController

    _gpio_mask: int
    _gpio_dir: int
    _port_val: int

    _trans_out: bytearray
    _trans_in: bytearray

    def __init__(self, gpio: GpioBaseController):
        self._gpio = gpio
        self._ftdi = self._gpio.ftdi
        self._port_val = 0
        self._trans_out = bytearray()
        self._trans_in = bytearray()

    @property
    def _bus_mask(self) -> int:
        raise NotImplementedError()

    @property
    def _bus_dir(self) -> int:
        raise NotImplementedError()

    def close(self, freeze: bool = False) -> None:
        self._gpio.close(freeze)
        self._frequency = 0.0

    def _read_raw(self, read_high: bool) -> int:
        # should not be used by anything
        raise NotImplementedError()

    def _write_raw(self, data: int, write_high: bool) -> None:
        # should not be used by anything
        raise NotImplementedError()

    def _flush(self) -> None:
        pass

    def read_gpio(self, with_output: bool = False) -> int:
        with self._lock:
            if isinstance(self._gpio, GpioAsyncController):
                value = self._gpio.read()
            elif isinstance(self._gpio, GpioSyncController):
                value = self._gpio.exchange(bytes([self._port_val]))[0]
            else:
                raise NotImplementedError()
            self._port_val = value
            value &= self._gpio_mask
            if not with_output:
                value &= ~self._gpio_dir
        return value

    def write_gpio(self, value: int) -> None:
        if (value & self._gpio_dir) != value:
            raise IOError("No such GPO pins: %04x/%04x" % (self._gpio_dir, value))
        with self._lock:
            self._port_val &= ~self._gpio_dir
            self._port_val |= value & self._gpio_dir
            if isinstance(self._gpio, GpioAsyncController):
                self._gpio.write(self._port_val)
            elif isinstance(self._gpio, GpioSyncController):
                self._gpio.exchange(bytes([self._port_val]))
            else:
                raise NotImplementedError()

    def _read_bus(self) -> int:
        with self._lock:
            if isinstance(self._gpio, GpioAsyncController):
                value = self._gpio.read()
            elif isinstance(self._gpio, GpioSyncController):
                value = self._trans_in.pop(0)
            else:
                raise NotImplementedError()
            self._port_val = value
            value &= self._bus_mask
        return value

    def _write_bus(self, value: int) -> None:
        with self._lock:
            self._port_val &= ~self._bus_dir
            self._port_val |= value & self._bus_dir
            if isinstance(self._gpio, GpioAsyncController):
                self._gpio.write(self._port_val)
            elif isinstance(self._gpio, GpioSyncController):
                self._trans_out.append(self._port_val)
            else:
                raise NotImplementedError()

    def _exchange_bus(self) -> None:
        if not isinstance(self._gpio, GpioSyncController):
            return
        if not self._trans_out:
            self._trans_in.clear()
            return
        # send transactions in chunks, otherwise a USB timeout may occur
        self._trans_in.clear()
        chunk_size = 372
        for i in range(0, len(self._trans_out), chunk_size):
            chunk = self._trans_out[i : i + chunk_size]
            self._trans_in += self._gpio.exchange(chunk)
        self._trans_out.clear()

    def _write_high(self, pin: int) -> None:
        self._write_bus(self._port_val | pin)

    def _write_low(self, pin: int) -> None:
        self._write_bus(self._port_val & ~pin)

    def _read_pin(self, pin: int) -> bool:
        return bool(self._read_bus() & pin)
