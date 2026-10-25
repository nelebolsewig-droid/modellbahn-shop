"""Public contract of the sales module: the only part other modules may import.

* :mod:`.events` - the order events other modules react to (inventory will allocate
  stock for paid orders). Framework-free, so any layer may use it.

This package itself imports nothing, so importing it loads no submodule.
"""
