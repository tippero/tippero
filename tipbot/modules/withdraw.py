#!/bin/python
#
# Cryptonote tipbot - withdrawal commands
# Copyright 2014,2015 moneromooo
# DNS code largely copied from Electrum OpenAlias plugin, Copyright 2014-2015 The monero Project
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import redis
import json
import string
import re
import dns.name
import dns.dnssec
import dns.resolver
import dns.message
import dns.query
import dns.rdatatype
import dns.rdtypes.ANY.TXT
import dns.rdtypes.ANY.NS
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
import tipbot.config as config
from tipbot.user import User
from tipbot.link import Link
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
    DisableWithdraw(None,None)

def ValidateDNSSEC(address):
  log_info('Validating DNSSEC for %s' % address)
  try:
    resolver = dns.resolver.get_default_resolver()
    ns = resolver.nameservers[0]
    parts = address.split('.')
    for i in xrange(len(parts),0,-1):
      subpart = '.'.join(parts[i-1:])
      query = dns.message.make_query(subpart,dns.rdatatype.NS)
      response = dns.query.udp(query,ns,1)
      if response.rcode() != dns.rcode.NOERROR:
        return False
      if len(response.authority) > 0:
        rrset = response.authority[0]
      else:
        rrset = response.answer[0]
      rr = rrset[0]
      if rr.rdtype == dns.rdatatype.SOA:
        continue
      query = dns.message.make_query(subpart,dns.rdatatype.DNSKEY,want_dnssec=True)
      response = dns.query.udp(query,ns,1)
      if response.rcode() != 0:
        return False
      answer = response.answer
      if len(answer) != 2:
        return False
      name = dns.name.from_text(subpart)
      dns.dnssec.validate(answer[0],answer[1],{name:answer[0]})
      return True
  except Exception,e:
    log_error('Failed to validate DNSSEC for %s: %s' % (address, str(e)))
    return False

def ResolveCore(address,ctype):
  log_info('Resolving %s address for %s' % (ctype,address))
  address=address.replace('@','.')
  if not '.' in address:
    return False,'invalid address'

  try:
    for attempt in range(3):
      resolver = dns.resolver.Resolver()
      resolver.timeout = 2
      resolver.lifetime = 2
      records = resolver.query(address,dns.rdatatype.TXT)
      for record in records:
        s = record.strings[0]
        if s.lower().startswith('oa1:%s' % ctype.lower()):
          a = re.sub('.*recipient_address[ \t]*=[ \t]*\"?([A-Za-z0-9]+)\"?.*','\\1',s)
          if IsValidAddress(a):
            log_info('Found %s address at %s: %s' % (ctype,address,a))
            return True, [a,ValidateDNSSEC(address)]
  except Exception,e:
    log_error('Error resolving %s: %s' % (address,str(e)))

  return False, 'not found'

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
    link.send("Usage: withdraw address [amount] [paymentid]")
    return

  if '.' in address:
    ok,extra=ResolveCore(address,coinspecs.symbol)
    if not ok:
      link.send('Error: %s' % extra)
      return
    a=extra[0]
    dnssec=extra[1]
    if not dnsssec:
      link.send('%s address %s was found for %s' % (coinspecs.name,a,address))
      link.send('Trust chain could not be verified, so withdrawal was not automatically performed')
      link.send('Withdraw using this %s address if it is correct' % coinspecs.name)
      return
    address=a

  if not IsValidAddress(address):
    link.send("Invalid address")
    return

  if GetParam(cmd,3):
    amount = GetParam(cmd,2)
    paymentid = GetParam(cmd,3)
  else:
    if IsValidPaymentID(GetParam(cmd,2)):
      amount = None
      paymentid = GetParam(cmd,2)
    else:
      amount = GetParam(cmd,2)
      paymentid = None

  if amount:
    try:
      amount = StringToUnits(amount)
      if (amount <= 0):
        raise RuntimeError("")
      amount += local_withdraw_fee
    except Exception,e:
      link.send("Invalid amount")
      return
  if paymentid != None:
    if not IsValidPaymentID(paymentid):
      link.send("Invalid payment ID")
      return

  log_info("Withdraw: %s wants to withdraw %s to %s" % (identity, AmountToString(amount) if amount else "all", address))

  if withdraw_disabled:
    log_error('Withdraw: disabled')
    link.send("Sorry, withdrawal is disabled due to a wallet error which requires admin assistance")
    return

  account = GetAccount(identity)
  try:
    balance = redis_hget('balances',account)
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
      'payment_id': paymentid,
      'fee': coinspecs.min_withdrawal_fee,
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

def Resolve(link,cmd):
  try:
    address=GetParam(cmd,1)
    if not address:
      raise RuntimeError("")
  except Exception,e:
    link.send('usage: !resolve <address>')
    return
  ok,extra=ResolveCore(address,coinspecs.symbol)
  if not ok:
    link.send('Error: %s' % extra)
    return
  a=extra[0]
  dnssec=extra[1]
  if dnssec:
    link.send('Found %s address at %s: %s' % (coinspecs.symbol,address,a))
  else:
    link.send('Found %s address at %s via insecure DNS: %s' % (coinspecs.symbol,address,a))

def Help(link):
  fee = config.withdrawal_fee or coinspecs.min_withdrawal_fee
  min_amount = config.min_withdraw_amount or fee
  link.send_private("Partial or full withdrawals can be made to any %s address" % coinspecs.name)
  link.send_private("OpenAlias is supported, to pay directly to a domain name which uses it")
  link.send_private("Minimum withdrawal: %s" % AmountToString(min_amount))
  link.send_private("Withdrawal fee: %s" % AmountToString(fee))



RegisterModule({
  'name': __name__,
  'help': Help,
})
RegisterCommand({
  'module': __name__,
  'name': 'withdraw',
  'parms': '<address>|<domain-name> [<amount>] [paymentid]',
  'function': Withdraw,
  'registered': True,
  'help': "withdraw part or all of your balance"
})
RegisterCommand({
  'module': __name__,
  'name': 'resolve',
  'parms': '<address>',
  'function': Resolve,
  'registered': True,
  'help': "Resolve a %s address from DNS with OpenAlias" % coinspecs.name
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
