#!/bin/python
#
# Cryptonote tipbot - withdrawal commands
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import redis
import json
import string
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
import tipbot.config as config
from tipbot.utils import *
from tipbot.redisdb import *
from tipbot.command_manager import *

withdraw_disabled = False

def DisableWithdraw(link,cmd):
  global withdraw_disabled
  if link:
    log_warn('DisableWithdraw: disabled by %s' % link.identity())
  else:
    log_warn('DisableWithdraw: disabled')
  withdraw_disabled = True

def EnableWithdraw(link,cmd):
  global withdraw_disabled
  log_info('EnableWithdraw: enabled by %s' % link.identity())
  withdraw_disabled = False

def CheckDisableWithdraw():
  if config.disable_withdraw_on_error:
    DisableWithdraw(None,None,None)

def Withdraw(link,cmd):
  identity=link.identity()

  local_withdraw_fee = config.withdrawal_fee or coinspecs.min_withdrawal_fee
  local_min_withdraw_amount = config.min_withdraw_amount or local_withdraw_fee

  if local_min_withdraw_amount <= 0 or local_withdraw_fee <= 0 or local_min_withdraw_amount < local_withdraw_fee:
    log_error('Withdraw: Inconsistent withdrawal settings')
    link.send("An error has occured")
    return

  try:
    address=cmd[1]
  except Exception,e:
    link.send("Usage: withdraw address [amount]")
    return

  if not IsValidAddress(address):
    link.send("Invalid address")
    return
  amount = GetParam(cmd,2)
  if amount:
    try:
      famount=float(amount)
      if (famount < 0):
        raise RuntimeError("")
      amount = long(famount * coinspecs.atomic_units)
      amount += local_withdraw_fee
    except Exception,e:
      link.send("Invalid amount")
      return

  log_info("Withdraw: %s wants to withdraw %s to %s" % (identity, AmountToString(amount) if amount else "all", address))

  if withdraw_disabled:
    log_error('Withdraw: disabled')
    link.send("Sorry, withdrawal is disabled due to a wallet error which requires admin assistance")
    return

  account = GetAccount(identity)
  try:
    balance = redis_hget('accounts',account)
    if balance == None:
      balance = 0
    balance=long(balance)
  except Exception, e:
    log_error('Withdraw: exception: %s' % str(e))
    link.send("An error has occured")
    return

  if amount:
    if amount > balance:
      log_info("Withdraw: %s trying to withdraw %s, but only has %s" % (identity,AmountToString(amount),AmountToString(balance)))
      link.send("You only have %s" % AmountToString(balance))
      return
  else:
    amount = balance

  if amount <= 0 or amount < local_min_withdraw_amount:
    log_info("Withdraw: Minimum withdrawal balance: %s, %s cannot withdraw %s" % (AmountToString(config.min_withdraw_amount),nick,AmountToString(amount)))
    link.send("Minimum withdrawal balance: %s, cannot withdraw %s" % (AmountToString(config.min_withdraw_amount),AmountToString(amount)))
    return
  try:
    fee = long(local_withdraw_fee)
    topay = long(amount - fee)
    log_info('Withdraw: Raw: fee: %s, to pay: %s' % (str(fee), str(topay)))
    log_info('Withdraw: fee: %s, to pay: %s' % (AmountToString(fee), AmountToString(topay)))
    params = {
      'destinations': [{'address': address, 'amount': topay}],
      'payment_id': GetPaymentID(link),
      'fee': fee,
      'mixin': config.withdrawal_mixin,
      'unlock_time': 0,
    }
    j = SendWalletJSONRPCCommand("transfer",params)
  except Exception,e:
    log_error('Withdraw: Error in transfer: %s' % str(e))
    CheckDisableWithdraw()
    link.send("An error has occured")
    return
  if not "result" in j:
    log_error('Withdraw: No result in transfer reply')
    CheckDisableWithdraw()
    link.send("An error has occured")
    return
  result = j["result"]
  if not "tx_hash" in result:
    log_error('Withdraw: No tx_hash in transfer reply')
    CheckDisableWithdraw()
    link.send("An error has occured")
    return
  tx_hash = result["tx_hash"]
  log_info('%s has withdrawn %s, tx hash %s' % (identity, amount, str(tx_hash)))
  link.send( "Tx sent: %s" % tx_hash)

  try:
    redis_hincrby("balances",account,-amount)
  except Exception, e:
    log_error('Withdraw: FAILED TO SUBTRACT BALANCE: exception: %s' % str(e))
    CheckDisableWithdraw()

def Help(link):
  fee = config.withdrawal_fee or coinspecs.min_withdrawal_fee
  min_amount = config.min_withdraw_amount or fee
  link.send_private("Minimum withdrawal: %s" % AmountToString(min_amount))
  link.send_private("Withdrawal fee: %s" % AmountToString(fee))



RegisterModule({
  'name': __name__,
  'help': Help,
})
RegisterCommand({
  'module': __name__,
  'name': 'withdraw',
  'parms': '<address> [<amount>]',
  'function': Withdraw,
  'registered': True,
  'help': "withdraw part or all of your balance"
})
RegisterCommand({
  'module': __name__,
  'name': 'enable_withdraw',
  'function': EnableWithdraw,
  'admin': True,
  'help': "Enable withdrawals"
})
RegisterCommand({
  'module': __name__,
  'name': 'disable_withdraw',
  'function': DisableWithdraw,
  'admin': True,
  'help': "Disable withdrawals"
})
