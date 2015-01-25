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

def IsBanned(link):
  try:
    banned = redis_hget('banned',link.identity())
    if not banned:
      return False, None
    banned = float(banned)
    now = time.time()
    if banned < now:
      redis_hdel('banned',link.identity())
      return False, None
    return True, 'You are banned for %s' % TimeToString(banned-now)
  except Exception,e:
    log_error('Failed to check bannishment for %s: %s' % (link.identity(),str(e)))
    return False, None

def IsBetValid(link,amount,minbet,maxbet,potential_loss,max_loss,max_loss_ratio):
  banned,reason = IsBanned(link)
  if banned:
    return False, reason
  try:
    amount = float(amount)
  except Exception,e:
    return False, "Invalid amount"
  units=long(amount*coinspecs.atomic_units)
  if units <= 0:
    return False, "Invalid amount"
  if maxbet != None and amount > maxbet:
    return False, "Max bet is %s" % AmountToString(maxbet * coinspecs.atomic_units)
  if minbet != None and amount < minbet:
    return False, "Min bet is %s" % AmountToString(minbet * coinspecs.atomic_units)

  enough, reason = IsPlayerBalanceAtLeast(link,units)
  if not enough:
    return False, reason

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
      log_info ('%s does not have enough balance' % link.user.nick)
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
  house_balance = unlocked_balance

  user_balances=0
  identities = redis_hgetall("balances")
  for identity in identities:
    ib = long(identities[identity])
    house_balance = house_balance - ib
    user_balances+=ib

  earmarked_balances=0
  earmarked = redis_hgetall("earmarked")
  for e in earmarked:
    eb = long(earmarked[e])
    house_balance = house_balance - eb
    earmarked_balances+=eb

  rbal=long(redis_get('reserve_balance') or 0)
  if rbal:
    house_balance = house_balance - rbal

  if house_balance < 0:
    raise RuntimeError('Negative house balance')
    return
  log_info('RetrieveHouseBalance: unlocked %s, users %s, earmarked %s, reserve %s, house %s' % (AmountToString(unlocked_balance), AmountToString(user_balances), AmountToString(earmarked_balances), AmountToString(rbal), AmountToString(house_balance)))
  return house_balance

def GetHouseBalance(link,cmd):
  try:
    balance = RetrieveHouseBalance()
    personal_balance=0
    for network in networks:
      identity=network.name+':'+config.tipbot_name
      personal_balance += long(redis_hget('balances',identity) or 0)
  except Exception,e:
    log_error('Failed to retrieve house balance: %s' % str(e))
    link.send('An error occured')
    return
  link.send('House balance: %s, %s personal balance: %s' % (AmountToString(balance), config.tipbot_name, AmountToString(personal_balance)))

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

def Ban(link,cmd):
  t = 3600
  try:
    sidentity = GetParam(cmd,1)
    if sidentity:
      sidentity=IdentityFromString(link,sidentity)
      if sidentity!=link.identity() and not IsAdmin(link):
        log_error('%s is not admin, cannot ban %s' % (link.identity(),sidentity))
        link.send('Access denied')
        return
    else:
      sidentity=link.identity()

    banned = redis_hget('banned',sidentity)
    now=time.time()
    if banned and float(banned) > now+t:
      link.send('%s is already banned for %s' % (NickFromIdentity(sidentity), TimeToString(banned-now)))
    else:
      redis_hset('banned',sidentity,now+t)
      link.send('%s is banned for %s' % (NickFromIdentity(sidentity), TimeToString(t)))
  except Exception,e:
    log_error('Failed to ban %s: %s' % (sidentity,str(e)))
    link.send('An error occured')
    return

def Unban(link,cmd):
  try:
    sidentity=GetParam(cmd,1)
    if not sidentity:
      sidentity=link.identity()
    sidentity=IdentityFromString(link,sidentity)
    redis_hdel('banned',sidentity)
    link.send('%s was unbanned' % (NickFromIdentity(sidentity)))
  except Exception,e:
    log_error('Failed to unban %s: %s' % (sidentity,str(e)))
    link.send('An error occured')
    return

def Report(link,cmd):
  GetHouseBalance(link,cmd)
  games=[]
  try:
    keys=redis_keys('*:zstats:daily:*')
    for key in keys:
      game=key.split(':')[0]
      if game not in games:
        games.append(game)
  except Exception,e:
    log_error('Failed to enumerate games: %s' % str(e))
    link.send('Failed to enumerate games')
    return
  now=datetime.datetime.utcnow()
  for game in games:
    try:
      ShowGameStats(link,'',game,game)
      period={1:'yesterday',7:'last week',30:'last month'}
      zdtname="%s:zstats:daily:"%game
      bets=0
      wagered=0
      won=0
      lost=0
      for days in range(1,31):
        ts=now-datetime.timedelta(days=days)
        tsd="%u-%02u-%02u" % (ts.year,ts.month,ts.day)
        bets+=long(redis_zscore(zdtname+"bets",tsd) or 0)
        wagered+=long(redis_zscore(zdtname+"wagered",tsd) or 0)
        won+=long(redis_zscore(zdtname+"won",tsd) or 0)
        lost+=long(redis_zscore(zdtname+"lost",tsd) or 0)
        if days in period.keys():
          if won>lost:
            wonlost='lost'
            balance_change=AmountToString(won-lost)
          else:
            wonlost='won'
            balance_change=AmountToString(lost-won)
          link.send('%s, %s: %d bets, %s wagered, house %s %s' % (game,period[days],bets,AmountToString(wagered),wonlost,balance_change))
    except Exception,e:
      log_error('Failed to generate report for %s: %s' % (game,str(e)))
      link.send('Failed to generate report for %s' % game)

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
RegisterCommand({
  'module': 'betting',
  'name': 'ban',
  'function': Ban,
  'registered': True,
  'help': "ban yourself from playing for an hour"
})
RegisterCommand({
  'module': 'betting',
  'name': 'unban',
  'function': Unban,
  'admin': True,
  'help': "unban someone from playing"
})
RegisterCommand({
  'module': 'betting',
  'name': 'report',
  'function': Report,
  'admin': True,
  'help': "Betting report"
})
