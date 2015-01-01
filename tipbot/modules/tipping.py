#!/bin/python
#
# Cryptonote tipbot - tipping commands
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import socket
import select
import random
import redis
import hashlib
import json
import httplib
import time
import string
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.utils import *
from tipbot.ircutils import *
from tipbot.command_manager import *
from tipbot.redisdb import *


def Tip(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  try:
    who=cmd[1]
    amount=float(cmd[2])
  except Exception,e:
    SendTo(sendto, "Usage: tip nick amount")
    return
  units=long(amount*coinspecs.atomic_units)
  if units <= 0:
    SendTo(sendto, "Invalid amount")
    return

  log_info("Tip: %s wants to tip %s %s" % (nick, who, AmountToString(units)))
  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(sendto, "You only have %s" % (AmountToString(balance)))
      return
    log_info('Tip: %s tipping %s %u units, with balance %u' % (nick, who, units, balance))
    try:
      p = redis_pipeline()
      p.hincrby("balances",nick,-units);
      p.hincrby("balances",who,units)
      p.execute()
      SendTo(sendto,"%s has tipped %s %s" % (nick, who, AmountToString(units)))
    except Exception, e:
      SendTo(sendto, "An error occured")
      return
  except Exception, e:
    log_error('Tip: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")

def Rain(nick,chan,cmd):
  userstable = GetUsersTable()

  if chan[0] != '#':
    SendTo(nick, "Raining can only be done in a channel")
    return

  try:
    amount=float(cmd[1])
  except Exception,e:
    SendTo(chan, "Usage: rain amount [users]")
    return
  users = GetParam(cmd,2)
  if users:
    try:
      users=long(users)
    except Exception,e:
      SendTo(chan, "Usage: rain amount [users]")
      return

  if amount <= 0:
    SendTo(chan, "Usage: rain amount [users]")
    return
  if users != None and users <= 0:
    SendTo(chan, "Usage: rain amount [users]")
    return
  units = long(amount * coinspecs.atomic_units)

  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(chan, "You only have %s" % (AmountToString(balance)))
      return

    log_log("userstable: %s" % str(userstable))
    userlist = userstable[chan].keys()
    userlist.remove(nick)
    for n in config.no_rain_to_nicks:
      userlist.remove(n)
    if users == None or users > len(userlist):
      users = len(userlist)
      everyone = True
    else:
      everyone = False
    if users == 0:
      SendTo(chan, "Nobody eligible for rain")
      return
    if units < users:
      SendTo(chan, "This would mean not even an atomic unit per nick")
      return
    log_info("%s wants to rain %s on %s users in %s" % (nick, AmountToString(units), users, chan))
    log_log("users in %s: %s" % (chan, str(userlist)))
    random.shuffle(userlist)
    userlist = userlist[0:users]
    log_log("selected users in %s: %s" % (chan, userlist))
    user_units = long(units / users)

    if everyone:
      msg = "%s rained %s on everyone in the channel" % (nick, AmountToString(user_units))
    else:
      msg = "%s rained %s on:" % (nick, AmountToString(user_units))
    pipe = redis_pipeline()
    pipe.hincrby("balances",nick,-units)
    for user in userlist:
      pipe.hincrby("balances",user,user_units)
      if not everyone:
        msg = msg + " " + user
    pipe.execute()
    SendTo(chan, "%s" % msg)

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    SendTo(chan, "An error has occured")
    return

def RainActive(nick,chan,cmd):
  userstable = GetUsersTable()

  amount=GetParam(cmd,1)
  hours=GetParam(cmd,2)
  minfrac=GetParam(cmd,3)

  if chan[0] != '#':
    SendTo(nick, "Raining can only be done in a channel")
    return
  try:
    amount=float(amount)
    if amount <= 0:
      raise RuntimeError("")
  except Exception,e:
    SendTo(chan, "Invalid amount")
    return
  try:
    hours=float(hours)
    if hours <= 0:
      raise RuntimeError("")
    seconds = hours * 3600
  except Exception,e:
    SendTo(chan, "Invalid hours")
    return
  if minfrac:
    try:
      minfrac=float(minfrac)
      if minfrac < 0 or minfrac > 1:
        raise RuntimeError("")
    except Exception,e:
      SendTo(chan, "minfrac must be a number between 0 and 1")
      return
  else:
    minfrac = 0

  units = long(amount * coinspecs.atomic_units)

  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      SendTo(chan, "You only have %s" % (AmountToString(balance)))
      return

    now = time.time()
    userlist = userstable[chan].keys()
    userlist.remove(nick)
    for n in config.no_rain_to_nicks:
      userlist.remove(n)
    weights=dict()
    weight=0
    for n in userlist:
      t = userstable[chan][n]
      if t == None:
        continue
      dt = now - t
      if dt <= seconds:
        w = (1 * (seconds - dt) + minfrac * dt) / (seconds)
        weights[n] = w
        weight += w

    if len(weights) == 0:
      SendTo(chan, "Nobody eligible for rain")
      return

    pipe = redis_pipeline()
    pipe.hincrby("balances",nick,-units)
    rained_units = 0
    nnicks = 0
    minu=None
    maxu=None
    for n in weights:
      user_units = long(units * weights[n] / weight)
      if user_units <= 0:
        continue
      log_info("%s rained %s on %s (last active %f hours ago)" % (nick, AmountToString(user_units),n,GetTimeSinceActive(chan,n)/3600))
      pipe.hincrby("balances",n,user_units)
      rained_units += user_units
      if not minu or user_units < minu:
        minu = user_units
      if not maxu or user_units > maxu:
        maxu = user_units
      nnicks = nnicks+1

    if maxu == None:
      SendTo(chan, "This would mean not even an atomic unit per nick")
      return

    pipe.execute()
    log_info("%s rained %s - %s (total %s, acc %s) on the %d nicks active in the last %f hours" % (nick, AmountToString(minu), AmountToString(maxu), AmountToString(units), AmountToString(rained_units), nnicks, hours))
    SendTo(chan, "%s rained %s - %s on the %d nicks active in the last %f hours" % (nick, AmountToString(minu), AmountToString(maxu), nnicks, hours))

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    SendTo(chan, "An error has occured")
    return


RegisterCommand({
  'module': __name__,
  'name': 'tip',
  'parms': '<nick> <amount>',
  'function': Tip,
  'registered': True,
  'help': "tip another user"
})
RegisterCommand({
  'module': __name__,
  'name': 'rain',
  'parms': '<amount> [<users>]',
  'function': Rain,
  'registered': True,
  'help': "rain some coins on everyone (or just a few)"
})
RegisterCommand({
  'module': __name__,
  'name': 'rainactive',
  'parms': '<amount> [<hours>]',
  'function': RainActive,
  'registered': True,
  'help': "rain some coins on whoever was active recently"
})
