"""Public contract of the catalogue module: the only part other modules may import.

* :mod:`.events` - the catalogue events other modules react to (sales and inventory
  will follow published and archived products). Framework-free, so any layer may use it.

This package itself imports nothing, so importing it loads no submodule.
"""
