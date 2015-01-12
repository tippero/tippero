#!/bin/python
#
# Cryptonote tipbot - configuration
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

tipbot_name = "monero-testnet-tipbot"

irc_network = 'irc.freenode.net'
irc_port = 6697
irc_send_delay = 0.4
irc_welcome_line = 'Welcome to the freenode Internet Relay Chat Network'
irc_channels = ['#txtptest000']
irc_timeout_seconds = 600
irc_use_ssl = True
irc_use_sasl = True
irc_sasl_name = "monero-tipbot"

redis_host="127.0.0.1"
redis_port=7777

daemon_host = 'testfull.monero.cc' # '127.0.0.1'
daemon_port = 28081 # 6060
wallet_host = '127.0.0.1'
wallet_port = 6061
wallet_update_time = 30 # seconds
withdrawal_fee=None # None defaults to the network default fee
min_withdraw_amount = None # None defaults to the withdrawal fee
withdrawal_mixin=0
disable_withdraw_on_error = True

admins = ["moneromooo", "moneromoo"]

# list of nicks to ignore for rains - bots, trolls, etc
no_rain_to_nicks = []

dice_edge = 0.01
dice_max_bet = 5
dice_min_bet = 0.001
# how much are we prepared to lose
dice_max_loss = 10
# how much are we prepared to lose as a ratio of our current pot
dice_max_loss_ratio = 0.05

