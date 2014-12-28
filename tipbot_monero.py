#!/bin/python
#
# Cryptonote tipbot - monero setup
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

coin_name="Monero"
coin=1e12
coin_denominations = [[1000000, 1, "piconero"], [1000000000, 1e6, "micronero"], [1000000000000, 1e9, "millinero"]]
address_length = [95, 95] # min/max size of addresses
address_prefix = ['4', '9'] # allowed prefixes of addresses
min_withdrawal_fee = 10000000000
web_wallet_url = "https://mymonero.com/" # None is there's none
