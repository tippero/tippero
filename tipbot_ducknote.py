#!/bin/python
#
# Cryptonote tipbot - ducknote setup
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

coin_name="Darknote"
coin=1e8
coin_denominations = []
address_length = [95, 98] # min/max size of addresses
address_prefix = ['dd'] # allowed prefixes of addresses
min_withdrawal_fee = 0.1
web_wallet_url = None
