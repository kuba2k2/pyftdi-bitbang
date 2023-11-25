# pyftdi-bitbang

Bit-bang protocol support for [PyFtdi](https://github.com/eblot/pyftdi).

This package adds SPI protocol support for FT232 devices without MPSSE 
(e.g. FT232RL) by using the bit-bang mode based on asynchronous 
or synchronous GPIO driver.

## Usage

*Refer to `tests/` for code examples.*

The library supports the following baud rates:

- in async mode: 57600..921600; only standard baud rates can be used (115200, 230400, etc.)
- in sync mode: 500..2000000; try to stick with "even" rates (aligned to thousands)

### SPI

The library provides a subclass of `SpiController` called `BitBangSpiController` 
which can be used as a drop-in replacement. It doesn't support features like CPOL/CPHA 
but should be enough for most applications.

Creating the object requires a GPIO controller: `GpioAsyncController` for fully software-driven
bit writing, or `GpioSyncController` to use a (much faster) transaction-based GPIO control.

Example of reading SPI flash ID:

```python
from pyftdi.gpio import GpioSyncController
from pyftdibb.spi import BitBangSpiController

gpio = GpioSyncController()
spi = BitBangSpiController(gpio=gpio)
spi.configure("ftdi:///1", frequency=1_000_000)
port = spi.get_port(cs=0)
# half-duplex mode
flash_id = port.exchange(b"\x9F", readlen=3, duplex=False)
# full-duplex mode (no benefit here, just an example)
flash_id = port.exchange(b"\x9F", readlen=4, duplex=True)
flash_id = flash_id[1:]
```

Example usage with [PySpiFlash](https://github.com/eblot/pyspiflash):

```python
from pyftdi.gpio import GpioSyncController
from pyftdibb.spi import BitBangSpiController
from spiflash.serialflash import SerialFlashManager

gpio = GpioSyncController()
spi = BitBangSpiController(gpio=gpio)
spi.configure("ftdi:///1", frequency=1_000_000)
flash = SerialFlashManager.get_from_controller(spi)
data = flash.read(0, 0x1000)
```

## License

MIT
