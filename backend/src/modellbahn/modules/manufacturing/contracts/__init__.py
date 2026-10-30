"""Public contract of the manufacturing module: the only part other modules may import.

* :mod:`.events` - the manufacturing events other modules react to (the stock books the
  good parts of a finished plate). Framework-free, so any layer may use it.
* :mod:`.part_numbers` - the format of part numbers, for the scanner. Framework-free.
* :mod:`.parts` - a read-only facade for the stock: parts, bills of materials and what a
  finished plate yielded. It queries the database and therefore belongs in another
  module's infrastructure layer.

This package itself imports nothing, so importing it loads no submodule.
"""
