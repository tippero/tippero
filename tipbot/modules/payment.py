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

last_wallet_update_time = None

def UpdateCoin(param):
  irc = param[0]
  redisdb = param[1]

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
        log_info('UpdateCoin: Got %d payments' % len(payments))
        for p in payments:
          log_log('UpdateCoin: Looking at payment %s' % str(p))
          bh = p["block_height"]
          if bh > scan_block_height:
            scan_block_height = bh
        log_log('UpdateCoin: seen payments up to block %d' % scan_block_height)
        try:
          pipe = redis_pipeline()
          pipe.set("scan_block_height", scan_block_height)
          log_log('UpdateCoin: processing payments')
          for p in payments:
            payment_id=p["payment_id"]
            tx_hash=p["tx_hash"]
            amount=p["amount"]
            try:
              recipient = GetNickFromPaymendID(payment_id)
              log_info('UpdateCoin: Found payment %s to %s for %s' % (tx_hash,recipient, AmountToString(amount)))
              pipe.hincrby("balances",recipient,amount);
            except Exception,e:
              log_error('UpdateCoin: No nick found for payment id %s, tx hash %s, amount %s' % (payment_id, tx_hash, amount))
          log_log('UpdateCoin: Executing received payments pipeline')
          pipe.execute()
        except Exception,e:
          log_error('UpdateCoin: failed to set scan_block_height: %s' % str(e))
      else:
        log_log('UpdateCoin: No payments in get_bulk_payments reply')
    else:
      log_error('UpdateCoin: No results in get_bulk_payments reply')
  except Exception,e:
    log_error('UpdateCoin: Failed to get bulk payments: %s' % str(e))
  last_wallet_update_time = time.time()

RegisterIdleFunction(UpdateCoin)

