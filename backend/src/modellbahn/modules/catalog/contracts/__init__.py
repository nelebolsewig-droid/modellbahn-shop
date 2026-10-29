"""Public contract of the catalogue module: the only part other modules may import.

* :mod:`.events` - the catalogue events other modules react to (sales and inventory
  will follow published and archived products). Framework-free, so any layer may use it.
* :mod:`.variants` - a read-only facade for the variants on sale (current price, title,
  best image) that carts and orders use. It queries the database and therefore belongs
  in another module's application or infrastructure layer.
* :mod:`.listings` - a read-only facade for marketplaces: a product in one scale as an
  offer elsewhere shows it.
* :mod:`.product_scales` - a read-only facade for manufacturing: the scales, and a
  product in one scale with the key its bill of materials refers to.

This package itself imports nothing, so importing it loads no submodule.
"""
