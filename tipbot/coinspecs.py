#!/bin/python
#
# Cryptonote tipbot - coins specifications
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

coinspecs = {
  "monero": {
    "name": "Monero",
    "symbol": "XMR",
    "atomic_units": 1e12,
    "denominations": [[1000000, 1, "piconero"], [1000000000, 1e6, "micronero"], [1000000000000, 1e9, "millinero"]],
    "address_length": [[95, 95], [106, 106]], # min/max size of addresses
    "address_prefix": ['4', '8', '9', 'A'], # allowed prefixes of addresses
    "min_withdrawal_fee": 10000000000,
    "web_wallet_url": "https://mymonero.com/", # None is there's none
  },
  "ducknote": {
    "name": "Darknote",
    "symbol": "XDN",
    "atomic_units": 1e8,
    "denominations": [],
    "address_length": [95, 98], # min/max size of addresses
    "address_prefix": ['dd'], # allowed prefixes of addresses
    "min_withdrawal_fee": 1000000,
    "web_wallet_url": None,
  },
  "dashcoin": {
    "name": "Dashcoin",
    "symbol": "DSH",
    "atomic_units": 1e8,
    "denominations": [],
    "address_length": [96], # min/max size of addresses
    "address_prefix": ['D'], # allowed prefixes of addresses
    "min_withdrawal_fee": 1000000,
    "web_wallet_url": None,
  },
  "monerito": {
    "name": "Monerito",
    "symbol": "XMR",
    "atomic_units": 1e6,
    "denominations": [[1000000000000000000, 1000000, "moneritos"]],
    "address_length": [95, 95], # min/max size of addresses
    "address_prefix": ['4', '9'], # allowed prefixes of addresses
    "min_withdrawal_fee": 10000000000,
    "web_wallet_url": "https://mymonero.com/", # None is there's none
  },
}

