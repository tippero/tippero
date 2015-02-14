#!/bin/python
#
# Cryptonote tipbot - pinata commands
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import os
import redis
import hashlib
import time
import string
import random
import math
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

def GetTarget(units):
  umod = long(config.pinata_target_increment * coinspecs.atomic_units + 0.5)
  units = long(float(units)+0.5)
  units -= units % umod
  return units

def PreparePinata(reset=False,units=None):
  p=redis_pipeline()
  if reset or not redis_hexists('pinata','target'):
    target=GetTarget((config.pinata_base_target+config.pinata_target_increment*random.randint(0,config.pinata_num_increments))*coinspecs.atomic_units)
    log_log('PreparePinata: target %s' % target)
    p.hset('pinata','target',target)
  if reset or not redis_hexists('pinata','units'):
    units=long(units or config.pinata_start_amount*coinspecs.atomic_units)
    if units < config.pinata_start_amount*coinspecs.atomic_units:
      units = long(config.pinata_start_amount*coinspecs.atomic_units)
    p.hset('pinata','units',units)
    p.hincrby('pinata','profit',-units)
    p.hincrby('earmarked','pinata',units)
  p.execute()

def Pinata(link,cmd):
  # Make sure there is always one
  PreparePinata()

  identity=link.identity()
  group=link.group
  if not group:
    link.send("There is no pinata around, they only appear in IRC channels")
    return

  try:
    pinata_units = long(redis_hget('pinata','units'))
  except Exception,e:
    log_error('Failed to get pinata units: %s' % str(e))
    link.send('An error occured')
    return

  min_target=GetTarget(config.pinata_base_target*coinspecs.atomic_units)
  max_target=GetTarget((config.pinata_base_target+(config.pinata_num_increments-1)*config.pinata_target_increment)*coinspecs.atomic_units)

  if not GetParam(cmd,1):
    min_win_units = (pinata_units + config.pinata_base_target*coinspecs.atomic_units) * config.pinata_winner_base_share
    link.send("The pinata is filled with %s, and can be hit with %s - %s (in increments of %s) - min win %s" % (AmountToString(pinata_units),AmountToString(min_target),AmountToString(max_target),AmountToString(config.pinata_target_increment*coinspecs.atomic_units),AmountToString(min_win_units)))
    return

  try:
    amount=float(cmd[1])
    units=long(amount*coinspecs.atomic_units+0.5)
    aim = GetTarget(units)
  except Exception,e:
    link.send("Usage: !pinata <amount>")
    return
  if aim < min_target:
    link.send("The pinata can only be hit by at least %s" % AmountToString(min_target))
    return
  if aim > max_target:
    link.send("The pinata can only be hit by at most %s" % AmountToString(max_target))
    return

  try:
    target = long(redis_hget('pinata','target'))
  except Exception,e:
    log_error('Failed to get pinata target: %s' % str(e))
    link.send('An error occured')
    return

  if target < min_target or target > max_target:
    log_error('Pinata target out of range: %s' % target)
    link.send('An error occured')
    return

  account = GetAccount(identity)
  log_info("Pinata: %s wants to swing %s at the pinata, aim is %d, target is %d" % (identity, amount, aim, target))
  valid,reason = IsBetValid(link,amount,None,None,0,0,0)
  if not valid:
    log_info("Pinata: %s's bet refused: %s" % (identity, reason))
    link.send("%s: %s" % (link.user.nick, reason))
    return

  try:
    if target==aim:
      log_info("Pinata: %s hits the pinata containing %s" % (identity, AmountToString(pinata_units)))

      winner_ratio = config.pinata_winner_base_share * aim / min_target
      rain_ratio = (1-winner_ratio) * config.pinata_rain_remainder_share
      carry_ratio = (1-winner_ratio) * config.pinata_carry_remainder_share
      winner_units = long(pinata_units * winner_ratio)
      rain_units = long(pinata_units * rain_ratio)
      carry_units = long(pinata_units * carry_ratio)
      profit_units = pinata_units - winner_units - rain_units

      log_log("Pinata: %s to winner, %s to rain, %s carry" % (AmountToString(winner_units),AmountToString(rain_units),AmountToString(carry_units)))

      p=redis_pipeline()
      p.hincrby('earmarked','pinata',-pinata_units)
      p.hincrby('balances',account,winner_units)
      link.send('%s swings at the pinata with %s and hits!' % (link.user.nick,AmountToString(units)))
      link.send('%s gets splashed by %s' % (link.user.nick,AmountToString(winner_units)))

      userlist=link.network.get_users(group.name)
      log_log("users in %s: %s" % (group.name,str([user.identity() for user in userlist])))
      userlist.remove(link)
      for n in config.no_rain_to_nicks:
        i=IdentityFromString(link,n)
        l=Link(link.network,User(link.network,NickFromIdentity(i)),group)
        if l in userlist:
          userlist.remove(l)

      if len(userlist) > 0:
        user_units = long(rain_units / len(userlist))
        log_log("The pinata rains %s on: %s" % (AmountToString(user_units),str([user.identity() for user in userlist])))
        link.send('%s rains on everyone else' % (AmountToString(user_units)))
        for n in userlist:
          a = GetAccount(n)
          p.hincrby('balances',a,user_units)

      p.hincrby('pinata','games',1)
      p.hincrby('pinata','profit',profit_units)
      p.execute()
      PreparePinata(True,carry_units)
      link.send('A new pinata appears filled with %s!' % AmountToString(carry_units))
    else:
      p=redis_pipeline()
      p.hincrby('balances',account,-units)
      p.hincrby('pinata','units',units)
      p.hincrby('earmarked','pinata',units)
      p.execute()
      link.send('%s swings at the pinata with %s and misses! The pinata now contains %s' % (link.user.nick,AmountToString(units),AmountToString(pinata_units+units)))
  except Exception,e:
    log_error('Pinata: error: %s' % str(e))
    link.send('An error occured')
    return

def PinataHelp(link):
  link.send_private("A pinata full of %s is floating in the air. Swing some %s at it!" % (coinspecs.name,coinspecs.name))
  link.send_private("This pinata can only be smashed by a secret amount of %s," % (coinspecs.name))
  min_target=GetTarget(config.pinata_base_target*coinspecs.atomic_units)
  max_target=GetTarget((config.pinata_base_target+(config.pinata_num_increments-1)*config.pinata_target_increment)*coinspecs.atomic_units)
  link.send_private("between %s and %s (inclusive), in %s increments" % (AmountToString(min_target),AmountToString(max_target),AmountToString(config.pinata_target_increment*coinspecs.atomic_units)))
  min_winner_share=config.pinata_winner_base_share
  max_winner_share=config.pinata_winner_base_share*(config.pinata_base_target+(config.pinata_num_increments-1)*config.pinata_target_increment)/config.pinata_base_target
  link.send_private("If you hit with the secret amount, it breaks and you get %u%% - %u%% of the %s in it," % (100*min_winner_share,100*max_winner_share,coinspecs.name))
  link.send_private("%u%% of the rest rains down on others in the channel, and %u%% are placed" % (100*config.pinata_rain_remainder_share,100*config.pinata_carry_remainder_share))
  link.send_private("in a new pinata. If you miss it, your %s end up in the pinata," % (coinspecs.name))
  link.send_private("increasing the bounty for next attempt")
  link.send_private("The winner's share is proportional to the amount of %s on the winning hit," % coinspecs.name)
  link.send_private("so you don't lose out by trying higher amounts")
  link.send_private("Remember, only one particular amount will manage to smash the pinata, try to find it!")



random.seed(time.time())
RegisterModule({
  'name': __name__,
  'help': PinataHelp,
})
RegisterCommand({
  'module': __name__,
  'name': 'pinata',
  'parms': '<amount-in-monero>',
  'function': Pinata,
  'registered': True,
  'help': "swing some %s at the pinata" % (coinspecs.name)
})
