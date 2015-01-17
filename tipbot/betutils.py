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
import tipbot.coinspecs as coinspecs
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

def IsPlayerBalanceAtLeast(nick,units):
  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      log_error ('%s does not have enough balance' % nick)
      return False, "You only have %s" % (AmountToString(balance))
  except Exception,e:
    log_error ('failed to query balance')
    return False, "Failed to query balance"
  return True, None

def SetServerSeed(nick,game,seed):
  try:
    redis_hset('%s:serverseed' % game,nick,seed)
    log_info('%s\'s %s server seed set' % (nick, game))
  except Exception,e:
    log_error('Failed to set %s server seed for %s: %s' % (game, nick, str(e)))
    raise

def GetServerSeed(nick,game):
  EnsureServerSeed(nick,game)
  try:
    return redis_hget('%s:serverseed' % game,nick)
  except Exception,e:
    log_error('Failed to get %s server seed for %s: %s' % (game, nick, str(e)))
    raise

def GenerateServerSeed(nick,game):
  try:
    salt="kfn3kjg4nkngvekjvn3u4vgb" + ":" + game
    s=salt+":"+nick+":"+str(time.time())+":"+str(random.randint(0,1000000))
    seed=hashlib.sha256(s).hexdigest()
    SetServerSeed(nick,game,seed)
  except Exception,e:
    log_error('Failed to generate %s server seed for %s: %s' % (game,nick,str(e)))
    raise

def EnsureServerSeed(nick,game):
  if not redis_hexists('%s:serverseed' % game,nick):
    GenerateServerSeed(nick,game)

def SetPlayerSeed(nick,game,seed):
  try:
    redis_hset('%s:playerseed' % game,nick,seed)
    log_info('%s\'s %s playerseed set to %s' % (nick, game, seed))
  except Exception,e:
    log_error('Failed to set %s player seed for %s: %s' % (game, nick, str(e)))
    raise

def GetPlayerSeed(nick,game):
  try:
    if not redis_hexists('%s:playerseed' % game,nick):
      return ""
    return redis_hget('%s:playerseed' % game,nick)
  except Exception,e:
    log_error('Failed to get %s player seed for %s: %s' % (game, nick, str(e)))
    raise

def GetServerSeedHash(nick,game):
  seed = GetServerSeed(nick,game)
  return hashlib.sha256(seed).hexdigest()

def RecordGameResult(nick,chan,game,win,lose,units):
  try:
    p = redis_pipeline()
    tname="%s:stats:"%game+nick
    rtname="%s:stats:reset:"%game+nick
    alltname="%s:stats:"%game
    p.hincrby(tname,"bets",1)
    p.hincrby(rtname,"bets",1)
    p.hincrby(alltname,"bets",1)
    p.hincrby(tname,"wagered",units)
    p.hincrby(rtname,"wagered",units)
    p.hincrby(alltname,"wagered",units)
    if win:
      p.hincrby("balances",nick,units)
      p.hincrby(tname,"won",units)
      p.hincrby(rtname,"won",units)
      p.hincrby(alltname,"won",units)
      p.hincrby(tname,"nwon",1)
      p.hincrby(rtname,"nwon",1)
      p.hincrby(alltname,"nwon",1)
    if lose:
      p.hincrby("balances",nick,-units)
      p.hincrby(tname,"lost",units)
      p.hincrby(rtname,"lost",units)
      p.hincrby(alltname,"lost",units)
      p.hincrby(tname,"nlost",1)
      p.hincrby(rtname,"nlost",1)
      p.hincrby(alltname,"nlost",1)
    p.execute()
  except Exception,e:
    log_error('RecordGameResult: exception updating redis: %s' % str(e))
    raise

def ShowGameStats(sendto,snick,title,game):
  tname="%s:stats:"%game+snick
  try:
    bets=redis_hget(tname,"bets")
    wagered=redis_hget(tname,"wagered")
    won=redis_hget(tname,"won")
    lost=redis_hget(tname,"lost")
    nwon=redis_hget(tname,"nwon")
    nlost=redis_hget(tname,"nlost")
  except Exception,e:
    log_error('Failed to retrieve %s stats for %s: %s' % (game, title, str(e)))
    SendTo(sendto,"An error occured")
    return
  if not bets:
    SendTo(sendto,"No %s stats available for %s" % (game,title))
    return

  bets = long(bets)
  wagered = long(wagered)
  won = long(won or 0)
  lost = long(lost or 0)
  nwon = long(nwon or 0)
  nlost = long(nlost or 0)

  if bets==0:
    SenTo(sendto,"No %s stats available for %s" % (game,title))
    return

  swagered = AmountToString(wagered)
  savg = AmountToString(wagered / bets)
  swon = AmountToString(won)
  slost = AmountToString(lost)
  if won >= lost:
    sov = "+" + AmountToString(won-lost)
  else:
    sov = "-" + AmountToString(lost-won)
  SendTo(sendto,"%s: %d games %d won, %d lost, %s wagered (average %s per game), %s won, %s lost, overall %s" % (title, bets, nwon, nlost, swagered, savg, swon, slost, sov))

def ResetGameStats(sendto,snick,game):
  try:
    p = redis_pipeline()
    tname="%s:stats:reset:"%game+snick
    bets=p.hset(tname,"bets",0)
    wagered=p.hset(tname,"wagered",0)
    won=p.hset(tname,"won",0)
    lost=p.hset(tname,"lost",0)
    nwon=p.hset(tname,"nwon",0)
    nlost=p.hset(tname,"nlost",0)
    p.execute()
    SendTo(sendto,"%s stats reset for %s" % (game,snick))
  except Exception,e:
    log_error('Error resetting %s stats for %s: %s' % (game,snick,str(e)))
    raise
