#!/bin/python
#
# Cryptonote tipbot - dice commands
# Copyright 2014,2015 moneromooo
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
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.utils import *
from tipbot.ircutils import *
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

def GetHouseBalance(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  try:
    balance = RetrieveHouseBalance()
  except Exception,e:
    log_error('Failed to retrieve house balance: %s' % str(e))
    SendTo(sendto, 'An error occured')
    return
  SendTo(sendto, 'House balance: %s' % AmountToString(balance))

def Roll(nick):
  try:
    if redis_hexists('dice:rolls',nick):
      rolls = redis_hget('dice:rolls',nick)
      rolls = long(rolls) + 1
    else:
      rolls = 1
  except Exception,e:
    log_error('Failed to prepare roll for %s: %s' % (nick, str(e)))
    raise

  try:
    s = GetServerSeed(nick,'dice') + ":" + GetPlayerSeed(nick,'dice') + ":" + str(rolls)
    sh = hashlib.sha256(s).hexdigest()
    roll = float(long(sh[0:8],base=16))/0x100000000
    return rolls, roll
  except Exception,e:
    log_error('Failed to roll for %s: %s' % (nick,str(e)))
    raise

def Dice(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)

  try:
    amount=float(cmd[1])
    units=long(amount*coinspecs.atomic_units)
    multiplier = float(cmd[2])
  except Exception,e:
    SendTo(sendto, "Usage: dice amount multiplier")
    return
  if multiplier < 0.1 or multiplier > 10:
    SendTo(sendto, "Invalid multiplier: should be between 0.1 and 10")
    return

  log_info("Dice: %s wants to bet %s at x%f" % (nick, AmountToString(units), multiplier))
  potential_loss = amount * multiplier
  valid,reason = IsBetAmountValid(amount,config.dice_min_bet,config.dice_max_bet,potential_loss,config.dice_max_loss,config.dice_max_loss_ratio)
  if not valid:
    log_info("Dice: %s's bet refused: %s" % (nick, reason))
    SendTo(sendto, "%s: %s" % (nick, reason))
    return

  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    balance=long(balance)
    if units > balance:
      log_error ('%s does not have enough balance' % nick)
      SendTo(sendto, "You only have %s" % (AmountToString(balance)))
      return
  except Exception,e:
    log_error ('failed to query balance')
    SendTo(sendto, "Failed to query balance")
    return

  try:
    rolls, roll = Roll(nick)
  except:
    SendTo(sendto,"An error occured")
    return

  target = (1 - config.dice_edge) / (1+multiplier)
  log_info("Dice: %s's #%d roll: %.16g, target %.16g" % (nick, rolls, roll, target))

  lose_units = units
  win_units = long(units * multiplier)
  log_log('units %s, multiplier %f, edge %f, lose_units %s, win_units %s' % (AmountToString(units), multiplier, config.dice_edge, AmountToString(lose_units), AmountToString(win_units)))
  win = roll <= target
  if win:
    msg = "%s wins %s on roll #%d! %.16g <= %.16g" % (nick, AmountToString(win_units), rolls, roll, target)
  else:
    msg = "%s loses %s on roll #%d. %.16g > %.16g" % (nick, AmountToString(lose_units), rolls, roll, target)

  try:
    RecordGameResult(nick,chan,"dice",win,not win,win_units if win else lose_units)
  except:
    return

  redis_hset("dice:rolls",nick,rolls)

  SendTo(nick, "%s" % msg)

def ShowDiceStats(sendto,snick,title):
  return ShowGameStats(sendto,snick,title,"dice")

def GetDiceStats(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  snick = GetParam(cmd,1)
  if snick and snick != nick:
    if not IsAdmin(nick):
      log_error('%s is not admin, cannot see dice stats for %s' % (nick, snick))
      SendTo(sendto,'Access denied')
      return
  else:
    snick=nick
  ShowDiceStats(sendto,snick,snick)
  ShowDiceStats(sendto,"reset:"+snick,'%s since reset' % snick)
  ShowDiceStats(sendto,'','overall')

def ResetDiceStats(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  snick = GetParam(cmd,1)
  if snick and snick != nick:
    if not IsAdmin(nick):
      log_error('%s is not admin, cannot see dice stats for %s' % (nick, snick))
      SendTo(sendto,'Access denied')
      return
  else:
    snick=nick
  try:
    ResetGameStats(sendto,snick,"dice")
  except Exception,e:
    SendTo(sendto,"An error occured")

def PlayerSeed(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  fair_string = GetParam(cmd,1)
  if not fair_string:
    SendTo(nick, "Usage: !playerseed <string>")
    return
  try:
    SetPlayerSeed(nick,'dice',fair_string)
  except Exception,e:
    log_error('Failed to save player seed for %s: %s' % (nick, str(e)))
    SendTo(sendto, 'An error occured')

def FairCheck(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  try:
    seed = GetServerSeed(nick,'dice')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (nick,str(e)))
    SendTo(seed,'An error has occured')
    return
  try:
    GenerateServerSeed(nick,'dice')
  except Exception,e:
    log_error('Failed to generate server seed for %s: %s' % (nick,str(e)))
    SendTo(seed,'An error has occured')
    return
  SendTo(sendto, 'Your server seed was %s - it has now been reset; see !fair for details' % str(seed))

def Seeds(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  try:
    sh = GetServerSeedHash(nick,'dice')
    ps = GetPlayerSeed(nick,'dice')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (nick,str(e)))
    SendTo(seed,'An error has occured')
    return
  SendTo(sendto, 'Your server seed hash is %s' % str(sh))
  if ps == "":
    SendTo(sendto, 'Your have not set a player seed')
  else:
    SendTo(sendto, 'Your player seed hash is %s' % str(ps))

def Fair(nick,chan,cmd):
  SendTo(nick,"%s's dice betting is provably fair" % config.tipbot_name)
  SendTo(nick,"Your rolls are determined by three pieces of information:")
  SendTo(nick," - your server seed. You can see its hash with !seeds")
  SendTo(nick," - your player seed. Empty by default, you can set it with !playerseed")
  SendTo(nick," - the roll number, displayed with each bet you make")
  SendTo(nick,"To verify past rolls were fair, use !faircheck")
  SendTo(nick,"You will be given your server seed, and a new one will be generated")
  SendTo(nick,"for future rolls. Then follow these steps:")
  SendTo(nick,"Calculate the SHA-256 sum of serverseed:playerseed:rollnumber")
  SendTo(nick,"Take the first 8 characters of this sum to make an hexadecimal")
  SendTo(nick,"number, and divide it by 0x100000000. You will end up with a number")
  SendTo(nick,"between 0 and 1 which was your roll for that particular bet")
  SendTo(nick,"See !faircode for Python code implementing this check")

def FairCode(nick,chan,cmd):
  SendTo(nick,"This Python 2 code takes the seeds and roll number and outputs the roll")
  SendTo(nick,"for the corresponding game. Run it with three arguments: server seed,")
  SendTo(nick,"player seed (use '' if you did not set any), and roll number.")

  SendTo(nick,"import sys,hashlib,random")
  SendTo(nick,"try:")
  SendTo(nick,"  s=hashlib.sha256(sys.argv[1]+':'+sys.argv[2]+':'+sys.argv[3]).hexdigest()")
  SendTo(nick,"  roll = float(long(s[0:8],base=16))/0x100000000")
  SendTo(nick,"  print '%.16g' % roll")
  SendTo(nick,"except:")
  SendTo(nick,"  print 'need serverseed, playerseed, and roll number'")

def DiceHelp(nick,chan):
  SendTo(nick,"The dice module is a provably fair %s dice betting game" % coinspecs.name)
  SendTo(nick,"Basic usage: !dice <amount> <multiplier>")
  SendTo(nick,"The goal is to get a roll under a target that depends on your chosen multiplier")
  SendTo(nick,"See !fair and !faircode for a description of the provable fairness of the game")
  SendTo(nick,"See !faircheck to get the server seed to check past rolls were fair")



random.seed(time.time())
RegisterModule({
  'name': __name__,
  'help': DiceHelp,
})
RegisterCommand({
  'module': __name__,
  'name': 'dice',
  'parms': '<amount> <multiplier>',
  'function': Dice,
  'admin': True,
  'registered': True,
  'help': "start a dice game - house edge %.1f%%" % (float(config.dice_edge)*100)
})
RegisterCommand({
  'module': __name__,
  'name': 'stats',
  'parms': '[<name>]',
  'function': GetDiceStats,
  'admin': True,
  'registered': True,
  'help': "displays your dice stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'resetstats',
  'parms': '[<name>]',
  'function': ResetDiceStats,
  'admin': True,
  'registered': True,
  'help': "resets your dice stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'house_balance',
  'function': GetHouseBalance,
  'admin': True,
  'registered': True,
  'help': "get the house balance"
})
RegisterCommand({
  'module': __name__,
  'name': 'playerseed',
  'parms': '<string>',
  'function': PlayerSeed,
  'admin': True,
  'registered': True,
  'help': "set a custom seed to use in the hash calculation"
})
RegisterCommand({
  'module': __name__,
  'name': 'seeds',
  'function': Seeds,
  'admin': True,
  'registered': True,
  'help': "Show hash of your current server seed and your player seed"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircheck',
  'function': FairCheck,
  'admin': True,
  'registered': True,
  'help': "Check provably fair rolls"
})
RegisterCommand({
  'module': __name__,
  'name': 'fair',
  'function': Fair,
  'admin': True,
  'help': "describe the provably fair dice game"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircode',
  'function': FairCode,
  'admin': True,
  'help': "Show sample Python code to check bet fairness"
})
