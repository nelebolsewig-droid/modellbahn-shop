"""Public contract of the sales module: the only part other modules may import.

* :mod:`.events` - the order events other modules react to (inventory allocates stock
  for paid orders). Framework-free, so any layer may use it.
* :mod:`.orders` - a read-only facade for orders and their lines, for allocating and
  picking. It queries the database and therefore belongs in another module's
  application or infrastructure layer.

This package itself imports nothing, so importing it loads no submodule.
"""
