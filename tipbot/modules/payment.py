#!/bin/python
#
# Cryptonote tipbot - payment
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import redis
import time
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.utils import *
from tipbot.redisdb import *
from tipbot.command_manager import *

last_wallet_update_time = None

def GetTipbotAddress():
  try:
    j = SendWalletJSONRPCCommand("getaddress",None)
    if not "result" in j:
      log_error('GetTipbotAddress: No result found in getaddress reply')
      return None
    result = j["result"]
    if not "address" in result:
      log_error('GetTipbotAddress: No address found in getaddress reply')
      return None
    return result["address"]
  except Exception,e:
    log_error("GetTipbotAddress: Error retrieving %s's address: %s" % (config.tipbot_name, str(e)))
    return None

def UpdateCoin(data):
  global last_wallet_update_time
  if last_wallet_update_time == None:
    last_wallet_update_time = 0
  t=time.time()
  dt = t - last_wallet_update_time
  if dt < config.wallet_update_time:
    return
  try:
    try:
      scan_block_height = redis_get("scan_block_height")
      scan_block_height = long(scan_block_height)
    except Exception,e:
      log_error('Failed to get scan_block_height: %s' % str(e))
      last_wallet_update_time = time.time()
      return

    try:
      j = SendDaemonHTMLCommand("getheight")
    except Exception,e:
      log_error('UpdateCoin: error getting height: %s' % str(e))
      return
    if not "height" in j:
      log_error('UpdateCoin: error getting height: height not found in %s' % str(j))
      return
    try:
      height=long(j["height"])
    except Exception,e:
      log_error('UpdateCoin: error getting height: %s' % str(e))
      return

    full_payment_ids = redis_hgetall("paymentid")
    #print 'Got full payment ids: %s' % str(full_payment_ids)
    payment_ids = []
    for pid in full_payment_ids:
      payment_ids.append(pid)
    #print 'Got payment ids: %s' % str(payment_ids)
    params = {
      "payment_ids": payment_ids,
      "min_block_height": scan_block_height
    }
    j = SendWalletJSONRPCCommand("get_bulk_payments",params)
    #print 'Got j: %s' % str(j)
    if "result" in j:
      result = j["result"]
      if "payments" in result:
        payments = result["payments"]
        new_payments = []
        n_confirming = 0
        for p in payments:
          log_log('UpdateCoin: Looking at payment %s' % str(p))
          bh = p["block_height"]
          confirmations = height-1-bh
          if confirmations >= config.payment_confirmations:
            log_info('Payment %s is now confirmed' % str(p))
            new_payments.append(p)
          else:
            log_info('Payment %s has %d/%d confirmations' % (str(p),confirmations,config.payment_confirmations))
            n_confirming += 1
        payments=new_payments
        log_info('UpdateCoin: Got %d mature payments and %d confirming payments' % (len(payments),n_confirming))
        if len(payments) > 0:
          for p in payments:
            if bh > scan_block_height:
              scan_block_height = bh
          log_log('UpdateCoin: updated payments up to block %d' % scan_block_height)
          try:
            pipe = redis_pipeline()
            pipe.set("scan_block_height", scan_block_height)
            log_log('UpdateCoin: processing payments')
            for p in payments:
              payment_id=p["payment_id"]
              tx_hash=p["tx_hash"]
              amount=p["amount"]
              bh = p["block_height"]
              try:
                recipient = GetIdentityFromPaymentID(payment_id)
                if not recipient:
                  raise RuntimeError('Payment ID %s not found' % payment_id)
                log_info('UpdateCoin: Found payment %s to %s for %s' % (tx_hash,recipient, AmountToString(amount)))
                if bh < height-config.payment_confirmations:
                  pipe.hincrby("balances",recipient,amount)
                else:
                  log_log('%d/%d confirmations' % (height-1-bh,config.payment_confirmations))
              except Exception,e:
                log_error('UpdateCoin: No identity found for payment id %s, tx hash %s, amount %s: %s' % (payment_id, tx_hash, amount, str(e)))
            log_log('UpdateCoin: Executing received payments pipeline')
            pipe.execute()
          except Exception,e:
            log_error('UpdateCoin: failed to set scan_block_height: %s' % str(e))
    else:
      log_error('UpdateCoin: No results in get_bulk_payments reply')
  except Exception,e:
    log_error('UpdateCoin: Failed to get bulk payments: %s' % str(e))
  last_wallet_update_time = time.time()

def Deposit(link,cmd):
  Help(link)

def Help(link):
  link.send_private("You can send %s to your account:" % coinspecs.name);
  address=GetTipbotAddress() or 'ERROR'
  link.send_private("  Address: %s" % address)
  link.send_private("  Payment ID: %s" % GetPaymentID(link))

RegisterModule({
  'name': __name__,
  'help': Help,
  'idle': UpdateCoin
})
RegisterCommand({
  'module': __name__,
  'name': 'deposit',
  'function': Deposit,
  'help': "Show instructions about depositing %s" % coinspecs.name
})

