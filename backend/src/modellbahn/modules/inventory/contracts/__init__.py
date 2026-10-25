"""Public contract of the inventory module: the only part other modules may import.

* :mod:`.events` - the stock events other modules react to (planning will follow
  backorders). Framework-free, so any layer may use it.
* :mod:`.availability` - the availability rule (in stock, made to order, unavailable)
  and the picking progress of an order. Framework-free, so any layer may use it.
* :mod:`.stock` - a read-only facade for sales: free units per variant and how far the
  picking of an order has come. It queries the database and therefore belongs in
  another module's infrastructure layer.

This package itself imports nothing, so importing it loads no submodule.
"""
