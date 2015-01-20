#!/bin/python
#
# Cryptonote tipbot - tipping commands
# Copyright 2014, 2015 moneromooo
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
from tipbot.command_manager import *
from tipbot.redisdb import *

pending_confirmations=dict()

def PerformTip(link,whoid,units):
  identity=link.identity()
  try:
    balance = redis_hget("balances",identity)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      link.send("You only have %s" % (AmountToString(balance)))
      return
    log_info('Tip: %s tipping %s %u units, with balance %u' % (identity, whoid, units, balance))
    try:
      p = redis_pipeline()
      p.incrby("tips_total_count",1);
      p.incrby("tips_total_amount",units);
      p.hincrby("tips_count",identity,1);
      p.hincrby("tips_amount",identity,units);
      p.hincrby("balances",identity,-units);
      p.hincrby("balances",whoid,units)
      p.execute()
      link.send("%s has tipped %s %s" % (NickFromIdentity(identity), NickFromIdentity(whoid), AmountToString(units)))
    except Exception, e:
      log_error("Tip: Error updating redis: %s" % str(e))
      link.send("An error occured")
      return
  except Exception, e:
    log_error('Tip: exception: %s' % str(e))
    link.send("An error has occured")

def Tip(link,cmd):
  identity=link.identity()
  try:
    who=cmd[1]
    amount=float(cmd[2])
  except Exception,e:
    link.send("Usage: tip nick amount")
    return
  units=long(amount*coinspecs.atomic_units)
  if units <= 0:
    link.send("Invalid amount")
    return

  whoid = IdentityFromString(link,who)

  log_info("Tip: %s wants to tip %s %s" % (identity, whoid, AmountToString(units)))
  if link.group:
    userlist=[user.identity() for user in link.network.get_users(link.group.name)]
    log_log('users: %s' % str(userlist))
    if not whoid in userlist:
      link.send("%s is not in %s: if you really intend to tip %s, type !confirmtip before tipping again" % (who, link.group.name, who))
      pending_confirmations[identity]={'who': whoid, 'units': units}
      return
  pending_confirmations.pop(identity,None)
  PerformTip(link,whoid,units)

def ConfirmTip(link,cmd):
  identity=link.identity()
  if not identity in pending_confirmations:
    link.send("%s has no tip waiting confirmation" % NickFromIdentity(identity))
    return
  whoid=pending_confirmations[identity]['who']
  units=pending_confirmations[identity]['units']
  pending_confirmations.pop(identity,None)
  PerformTip(link,whoid,units)

def Rain(link,cmd):
  identity=link.identity()

  group=link.group
  if not group:
    link.send("Raining can only be done in a group")
    return

  try:
    amount=float(cmd[1])
  except Exception,e:
    link.send("Usage: rain amount [users]")
    return
  users = GetParam(cmd,2)
  if users:
    try:
      users=long(users)
    except Exception,e:
      link.send("Usage: rain amount [users]")
      return

  if amount <= 0:
    link.send("Usage: rain amount [users]")
    return
  if users != None and users <= 0:
    link.send("Usage: rain amount [users]")
    return
  units = long(amount * coinspecs.atomic_units)

  try:
    balance = redis_hget("balances",identity)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      link.send("You only have %s" % (AmountToString(balance)))
      return

    userlist=[user.identity() for user in link.network.get_users(group.name)]
    log_log("users in %s: %s" % (group.name,str(userlist)))
    userlist.remove(identity)
    for n in config.no_rain_to_nicks:
      userlist.remove(IdentityFromString(link,n))
    if users == None or users > len(userlist):
      users = len(userlist)
      everyone = True
    else:
      everyone = False
    if users == 0:
      link.send("Nobody eligible for rain")
      return
    if units < users:
      link.send("This would mean not even an atomic unit per nick")
      return
    log_info("%s wants to rain %s on %s users in %s" % (identity, AmountToString(units), users, group.name))
    log_log("eligible users in %s: %s" % (group.name, str(userlist)))
    random.shuffle(userlist)
    userlist = userlist[0:users]
    log_log("selected users in %s: %s" % (group.name, userlist))
    user_units = long(units / users)

    enumerate_users = False
    if everyone:
      msg = "%s rained %s on everyone in the channel" % (link.user.nick, AmountToString(user_units))
    elif len(userlist) > 16:
      msg = "%s rained %s on %d nicks" % (link.user.nick, AmountToString(user_units), len(userlist))
    else:
      msg = "%s rained %s on:" % (link.user.nick, AmountToString(user_units))
      enumerate_users = True
    pipe = redis_pipeline()
    pipe.hincrby("balances",identity,-units)
    pipe.incrby("rain_total_count",1)
    pipe.incrby("rain_total_amount",units)
    pipe.hincrby("rain_count",identity,1)
    pipe.hincrby("rain_amount",identity,units)
    for user in userlist:
      pipe.hincrby("balances",user,user_units)
      if enumerate_users:
        msg = msg + " " + NickFromIdentity(user)
    pipe.execute()
    link.send("%s" % msg)

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    link.send("An error has occured")
    return

def RainActive(link,cmd):
  identity=link.identity()

  amount=GetParam(cmd,1)
  hours=GetParam(cmd,2)
  minfrac=GetParam(cmd,3)

  group=link.group
  if not group:
    link.send("Raining can only be done in a channel")
    return
  if not amount or not hours:
    link.send("usage: !rainactive <amount> <hours> [<minfrac>]")
    return
  try:
    amount=float(amount)
    if amount <= 0:
      raise RuntimeError("")
  except Exception,e:
    link.send("Invalid amount")
    return
  try:
    hours=float(hours)
    if hours <= 0:
      raise RuntimeError("")
    seconds = hours * 3600
  except Exception,e:
    link.send("Invalid hours")
    return
  if minfrac:
    try:
      minfrac=float(minfrac)
      if minfrac < 0 or minfrac > 1:
        raise RuntimeError("")
    except Exception,e:
      link.send("minfrac must be a number between 0 and 1")
      return
  else:
    minfrac = 0

  units = long(amount * coinspecs.atomic_units)

  try:
    balance = redis_hget("balances",identity)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      link.send("You only have %s" % (AmountToString(balance)))
      return

    now = time.time()
    userlist = [user.identity() for user in link.network.get_active_users(seconds,group.name)]
    log_log('userlist: %s' % str(userlist))
    userlist.remove(link.identity())
    for n in config.no_rain_to_nicks:
      userlist.remove(IdentityFromString(link,n))
    weights=dict()
    weight=0
    log_log('userlist to loop: %s' % str(userlist))
    for n in userlist:
      log_log('user to check: %s' % NickFromIdentity(n))
      t = link.network.get_last_active_time(NickFromIdentity(n),group.name)
      if t == None:
        continue
      dt = now - t
      if dt <= seconds:
        w = (1 * (seconds - dt) + minfrac * dt) / (seconds)
        weights[n] = w
        weight += w

    if len(weights) == 0:
      link.send("Nobody eligible for rain")
      return

    pipe = redis_pipeline()
    pipe.hincrby("balances",identity,-units)
    pipe.incrby("arain_total_count",1);
    pipe.incrby("arain_total_amount",units);
    pipe.hincrby("arain_count",identity,1);
    pipe.hincrby("arain_amount",identity,units);
    rained_units = 0
    nnicks = 0
    minu=None
    maxu=None
    for n in weights:
      user_units = long(units * weights[n] / weight)
      if user_units <= 0:
        continue
      act = now - link.network.get_last_active_time(NickFromIdentity(n),link.group.name)
      log_info("%s rained %s on %s (last active %f hours ago)" % (identity, AmountToString(user_units),n,act/3600))
      pipe.hincrby("balances",n,user_units)
      rained_units += user_units
      if not minu or user_units < minu:
        minu = user_units
      if not maxu or user_units > maxu:
        maxu = user_units
      nnicks = nnicks+1

    if maxu == None:
      link.send("This would mean not even an atomic unit per nick")
      return

    pipe.execute()
    log_info("%s rained %s - %s (total %s, acc %s) on the %d nicks active in the last %s hours" % (identity, AmountToString(minu), AmountToString(maxu), AmountToString(units), AmountToString(rained_units), nnicks, TimeToString(seconds)))
    link.send("%s rained %s - %s on the %d nicks active in the last %s hours" % (identity, AmountToString(minu), AmountToString(maxu), nnicks, TimeToString(seconds)))

  except Exception,e:
    log_error('Rain: exception: %s' % str(e))
    link.send("An error has occured")
    return

def Help(link):
  link.send('You can tip other people, or rain %s on them' % coinspecs.name)
  link.send('!tip tips a single person, while !rain shares equally between people in the channel')
  link.send('!rainactive tips all within the last N hours, with more recently active people')
  link.send('getting a larger share.')


RegisterModule({
  'name': __name__,
  'help': Help,
})
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
  'name': 'confirmtip',
  'function': ConfirmTip,
  'registered': True,
  'help': "confirm a tip to another user who is not in the channel"
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
  'parms': '<amount> <hours> [<minfrac>]',
  'function': RainActive,
  'registered': True,
  'help': "rain some coins on whoever was active recently"
})
