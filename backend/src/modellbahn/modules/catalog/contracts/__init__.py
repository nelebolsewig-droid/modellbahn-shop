"""Public contract of the catalogue module: the only part other modules may import.

* :mod:`.events` - the catalogue events other modules react to (sales and inventory
  will follow published and archived products). Framework-free, so any layer may use it.
* :mod:`.variants` - a read-only facade for the variants on sale (current price, title,
  best image) that carts and orders use. It queries the database and therefore belongs
  in another module's application or infrastructure layer.

This package itself imports nothing, so importing it loads no submodule.
"""
