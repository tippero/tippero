#!/bin/python
#
# Cryptonote tipbot - dashcoin setup
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

coin_name="Dashcoin"
coin=1e8
coin_denominations = []
address_length = [96] # min/max size of addresses
address_prefix = ['D'] # allowed prefixes of addresses
min_withdrawal_fee = 0.01
web_wallet_url = None
