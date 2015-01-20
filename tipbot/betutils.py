#!/bin/python
#
# Cryptonote tipbot - bet utils
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import random
import hashlib
import time
import datetime
import tipbot.coinspecs as coinspecs
from tipbot.command_manager import *
from utils import *

def IsBetAmountValid(amount,minbet,maxbet,potential_loss,max_loss,max_loss_ratio):
  try:
    amount = float(amount)
  except Exception,e:
    return False, "Invalid amount"
  units=long(amount*coinspecs.atomic_units)
  if units <= 0:
    return False, "Invalid amount"
  if amount > maxbet:
    return False, "Max bet is %s" % AmountToString(maxbet * coinspecs.atomic_units)
  if amount < minbet:
    return False, "Min bet is %s" % AmountToString(minbet * coinspecs.atomic_units)
  if potential_loss > 0:
    if potential_loss > max_loss:
      return False, "Max potential loss is %s" % AmountToString(max_loss * coinspecs.atomic_units)
    try:
      house_balance = RetrieveHouseBalance()
    except Exception,e:
      log_error('Failed to get house balance: %s' % str(e))
      return False, "Failed to get house balance"
    max_floating_loss = max_loss_ratio * house_balance / coinspecs.atomic_units
    if potential_loss > max_floating_loss:
      return False, "Potential loss too large for house balance"

  return True, None

def IsPlayerBalanceAtLeast(link,units):
  try:
    balance = redis_hget("balances",link.identity())
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      log_error ('%s does not have enough balance' % link.user.nick)
      return False, "You only have %s" % (AmountToString(balance))
  except Exception,e:
    log_error ('failed to query balance')
    return False, "Failed to query balance"
  return True, None

def SetServerSeed(link,game,seed):
  identity=link.identity()
  try:
    redis_hset('%s:serverseed' % game,identity,seed)
    log_info('%s\'s %s serverseed set' % (identity, game))
  except Exception,e:
    log_error('Failed to set %s server seed for %s: %s' % (game, identity, str(e)))
    raise

def GetServerSeed(link,game):
  EnsureServerSeed(link,game)
  identity=link.identity()
  try:
    return redis_hget('%s:serverseed' % game,identity)
  except Exception,e:
    log_error('Failed to get %s server seed for %s: %s' % (game, identity, str(e)))
    raise

def GenerateServerSeed(link,game):
  identity=link.identity()
  try:
    salt="kfn3kjg4nkngvekjvn3u4vgb" + ":" + game
    s=salt+":"+identity+":"+str(time.time())+":"+str(random.randint(0,1000000))
    seed=hashlib.sha256(s).hexdigest()
    SetServerSeed(link,game,seed)
  except Exception,e:
    log_error('Failed to generate %s server seed for %s: %s' % (game,identity,str(e)))
    raise

def EnsureServerSeed(link,game):
  if not redis_hexists('%s:serverseed' % game,link.identity()):
    GenerateServerSeed(link,game)

def SetPlayerSeed(link,game,seed):
  identity=link.identity()
  try:
    redis_hset('%s:playerseed' % game,identity,seed)
    log_info('%s\'s %s playerseed set to %s' % (identity, game, seed))
  except Exception,e:
    log_error('Failed to set %s player seed for %s: %s' % (game, identity, str(e)))
    raise

def GetPlayerSeed(link,game):
  identity=link.identity()
  try:
    if not redis_hexists('%s:playerseed' % game,identity):
      return ""
    return redis_hget('%s:playerseed' % game,identity)
  except Exception,e:
    log_error('Failed to get %s player seed for %s: %s' % (game, identity, str(e)))
    raise

def GetServerSeedHash(link,game):
  seed = GetServerSeed(link,game)
  return hashlib.sha256(seed).hexdigest()

def RecordGameResult(link,game,win,lose,units):
  identity=link.identity()
  try:
    ts=datetime.datetime.utcnow()
    tsh="%u" % (ts.hour)
    tsd="%u-%02u-%02u" % (ts.year,ts.month,ts.day)
    p = redis_pipeline()
    tname="%s:stats:"%game+identity
    rtname="%s:stats:reset:"%game+identity
    alltname="%s:stats:"%game
    zhtname="%s:zstats:hourly:"%game
    zdtname="%s:zstats:daily:"%game
    p.hincrby(tname,"bets",1)
    p.hincrby(rtname,"bets",1)
    p.hincrby(alltname,"bets",1)
    p.zincrby(zhtname+"bets",tsh,1)
    p.zincrby(zdtname+"bets",tsd,1)
    p.hincrby(tname,"wagered",units)
    p.hincrby(rtname,"wagered",units)
    p.hincrby(alltname,"wagered",units)
    p.zincrby(zhtname+"wagered",tsh,units)
    p.zincrby(zdtname+"wagered",tsd,units)
    if win:
      p.hincrby("balances",identity,units)
      p.hincrby(tname,"won",units)
      p.hincrby(rtname,"won",units)
      p.hincrby(alltname,"won",units)
      p.zincrby(zhtname+"won",tsh,units)
      p.zincrby(zdtname+"won",tsd,units)
      p.hincrby(tname,"nwon",1)
      p.hincrby(rtname,"nwon",1)
      p.hincrby(alltname,"nwon",1)
      p.zincrby(zhtname+"nwon",tsh,1)
      p.zincrby(zdtname+"nwon",tsd,1)
    if lose:
      p.hincrby("balances",identity,-units)
      p.hincrby(tname,"lost",units)
      p.hincrby(rtname,"lost",units)
      p.hincrby(alltname,"lost",units)
      p.zincrby(zhtname+"lost",tsh,units)
      p.zincrby(zdtname+"lost",tsd,units)
      p.hincrby(tname,"nlost",1)
      p.hincrby(rtname,"nlost",1)
      p.hincrby(alltname,"nlost",1)
      p.zincrby(zhtname+"nlost",tsh,1)
      p.zincrby(zdtname+"nlost",tsd,1)
    p.execute()
  except Exception,e:
    log_error('RecordGameResult: exception updating redis: %s' % str(e))
    raise

def ShowGameStats(link,sidentity,title,game):
  identity=IdentityFromString(link,sidentity)
  tname="%s:stats:"%game+sidentity
  try:
    bets=redis_hget(tname,"bets")
    wagered=redis_hget(tname,"wagered")
    won=redis_hget(tname,"won")
    lost=redis_hget(tname,"lost")
    nwon=redis_hget(tname,"nwon")
    nlost=redis_hget(tname,"nlost")
  except Exception,e:
    log_error('Failed to retrieve %s stats for %s: %s' % (game, title, str(e)))
    link.send("An error occured")
    return
  if not bets:
    link.send("No %s stats available for %s" % (game,title))
    return

  bets = long(bets)
  wagered = long(wagered)
  won = long(won or 0)
  lost = long(lost or 0)
  nwon = long(nwon or 0)
  nlost = long(nlost or 0)

  if bets==0:
    link.send("No %s stats available for %s" % (game,title))
    return

  swagered = AmountToString(wagered)
  savg = AmountToString(wagered / bets)
  swon = AmountToString(won)
  slost = AmountToString(lost)
  if won >= lost:
    sov = "+" + AmountToString(won-lost)
  else:
    sov = "-" + AmountToString(lost-won)
  link.send("%s: %d games %d won, %d lost, %s wagered (average %s per game), %s won, %s lost, overall %s" % (title, bets, nwon, nlost, swagered, savg, swon, slost, sov))

def ResetGameStats(link,sidentity,game):
  identity=IdentityFromString(link,sidentity)
  try:
    p = redis_pipeline()
    tname="%s:stats:reset:"%game+sidentity
    bets=p.hset(tname,"bets",0)
    wagered=p.hset(tname,"wagered",0)
    won=p.hset(tname,"won",0)
    lost=p.hset(tname,"lost",0)
    nwon=p.hset(tname,"nwon",0)
    nlost=p.hset(tname,"nlost",0)
    p.execute()
    link.send("%s stats reset for %s" % (game,sidentity))
  except Exception,e:
    log_error('Error resetting %s stats for %s: %s' % (game,sidentity,str(e)))
    raise

def RetrieveHouseBalance():
  balance, unlocked_balance = RetrieveTipbotBalance()

  identities = redis_hgetall("balances")
  for identity in identities:
    ib = redis_hget("balances", identity)
    unlocked_balance = unlocked_balance - long(ib)
    log_log('RetrieveHouseBalance: subtracting %s from %s to give %s' % (AmountToString(ib), identity, AmountToString(unlocked_balance)))

  rbal=redis_get('reserve_balance')
  if rbal:
    unlocked_balance = unlocked_balance - long(rbal)
    log_log('RetrieveHouseBalance: subtracting %s reserve balance to give %s' % (AmountToString(rbal), AmountToString(unlocked_balance)))

  if unlocked_balance < 0:
    raise RuntimeError('Negative house balance')
    return
  return unlocked_balance

def GetHouseBalance(link,cmd):
  try:
    balance = RetrieveHouseBalance()
  except Exception,e:
    log_error('Failed to retrieve house balance: %s' % str(e))
    link.send('An error occured')
    return
  link.send('House balance: %s' % AmountToString(balance))

def ReserveBalance(link,cmd):
  rbal=GetParam(cmd,1)
  if rbal:
    try:
      rbal=float(cmd[1])
      if rbal < 0:
        raise RuntimeError('negative balance')
      rbal = long(rbal * coinspecs.atomic_units)
    except Exception,e:
      log_error('SetReserveBalance: invalid balance: %s' % str(e))
      link.send("Invalid balance")
      return

  try:
    current_rbal=long(redis_get('reserve_balance') or 0)
  except Exception,e:
    log_error('Failed to get current reserve balance: %s' % str(e))
    link.send("Failed to get current reserve balance")
    return
  if rbal == None:
    link.send("Reserve balance is %s" % AmountToString(current_rbal))
    return

  try:
    house_balance = RetrieveHouseBalance()
  except Exception,e:
    log_error('Failed to get house balance: %s' % str(e))
    link.send("Failed to get house balance")
    return
  if rbal > house_balance + current_rbal:
    log_error('Cannot set reserve balance higher than max house balance')
    link.send('Cannot set reserve balance higher than max house balance')
    return
  try:
    redis_set('reserve_balance',rbal)
  except Exception,e:
    log_error('Failed to set reserve balance: %s' % str(e))
    link.send("Failed to set reserve balance")
    return
  link.send("Reserve balance set")

RegisterCommand({
  'module': 'betting',
  'name': 'reserve_balance',
  'parms': '[<amount>]',
  'function': ReserveBalance,
  'admin': True,
  'help': "Set or get reserve balance (not part of the house balance)"
})
RegisterCommand({
  'module': 'betting',
  'name': 'house_balance',
  'function': GetHouseBalance,
  'admin': True,
  'registered': True,
  'help': "get the house balance"
})
