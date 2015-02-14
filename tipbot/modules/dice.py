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
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

def Roll(link):
  identity=link.identity()
  try:
    if redis_hexists('dice:rolls',identity):
      rolls = redis_hget('dice:rolls',identity)
      rolls = long(rolls) + 1
    else:
      rolls = 1
  except Exception,e:
    log_error('Failed to prepare roll for %s: %s' % (identity, str(e)))
    raise

  try:
    s = GetServerSeed(link,'dice') + ":" + GetPlayerSeed(link,'dice') + ":" + str(rolls)
    sh = hashlib.sha256(s).hexdigest()
    roll = float(long(sh[0:8],base=16))/0xffffffff
    return rolls, roll
  except Exception,e:
    log_error('Failed to roll for %s: %s' % (identity,str(e)))
    raise

def Dice(link,cmd):
  identity=link.identity()
  try:
    amount=float(cmd[1])
    units=StringToUnits(cmd[1])
    multiplier = float(cmd[2])
    overunder=GetParam(cmd,3)
  except Exception,e:
    link.send("Usage: dice amount multiplier [over|under]")
    return
  if multiplier < float(config.dice_min_multiplier) or multiplier > float(config.dice_max_multiplier):
    link.send("Invalid multiplier: should be between %f and %f" % (config.dice_min_multiplier, config.dice_max_multiplier))
    return
  if overunder == "over":
    under=False
  elif overunder == "under" or not overunder:
    under=True
  else:
    link.send("Usage: dice amount multiplier [over|under]")
    return

  log_info("Dice: %s wants to bet %s at x%f, %s target" % (identity, AmountToString(units), multiplier, "under" if under else "over"))
  potential_loss = amount * multiplier
  valid,reason = IsBetValid(link,amount,config.dice_min_bet,config.dice_max_bet,potential_loss,config.dice_max_loss,config.dice_max_loss_ratio)
  if not valid:
    log_info("Dice: %s's bet refused: %s" % (identity, reason))
    link.send("%s: %s" % (link.user.nick, reason))
    return

  try:
    rolls, roll = Roll(link)
  except:
    link.send("An error occured")
    return

  target = (1 - config.dice_edge) / multiplier
  if not under:
    target = 1 - target
  log_info("Dice: %s's #%d roll: %.16g, target %s %.16g" % (identity, rolls, roll, "under" if under else "over", target))

  lose_units = units
  win_units = long(units * multiplier) - lose_units
  log_log('units %s, multiplier %f, edge %f, lose_units %s, win_units %s' % (AmountToString(units), multiplier, config.dice_edge, AmountToString(lose_units), AmountToString(win_units)))
  if under:
    win = roll <= target
  else:
    win = roll >= target
  if win:
    msg = "%s bets %s and wins %s on roll #%d! %.16g %s %.16g" % (link.user.nick, AmountToString(lose_units), AmountToString(win_units+lose_units), rolls, roll, "<=" if under else ">=", target)
  else:
    msg = "%s bets %s and loses on roll #%d. %.16g %s %.16g" % (link.user.nick, AmountToString(lose_units), rolls, roll, ">" if under else "<", target)

  try:
    RecordGameResult(link,"dice",win,not win,win_units if win else lose_units)
  except:
    return

  redis_hset("dice:rolls",identity,rolls)

  link.send("%s" % msg)

def ShowDiceStats(link,sidentity,title):
  return ShowGameStats(link,sidentity,title,"dice")

def GetDiceStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see dice stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  ShowDiceStats(link,sidentity,NickFromIdentity(sidentity))
  ShowDiceStats(link,"reset:"+sidentity,'%s since reset' % NickFromIdentity(sidentity))
  ShowDiceStats(link,'','overall')

def ResetDiceStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see dice stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  try:
    ResetGameStats(link,sidentity,"dice")
  except Exception,e:
    link.send("An error occured")

def PlayerSeed(link,cmd):
  identity=link.identity()
  fair_string = GetParam(cmd,1)
  if not fair_string:
    link.send("Usage: !playerseed <string>")
    return
  try:
    SetPlayerSeed(link,'dice',fair_string)
  except Exception,e:
    log_error('Failed to save player seed for %s: %s' % (identity, str(e)))
    link.send('An error occured')
  try:
    ps = GetPlayerSeed(link,'dice')
  except Exception,e:
    log_error('Failed to retrieve newly set player seed for %s: %s' % (identity, str(e)))
    link.send('An error occured')
    return
  link.send('Your new player seed is: %s' % ps)

def FairCheck(link,cmd):
  identity=link.identity()
  try:
    seed = GetServerSeed(link,'dice')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  try:
    GenerateServerSeed(link,'dice')
  except Exception,e:
    log_error('Failed to generate server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  link.send('Your server seed was %s - it has now been reset; see !fair for details' % str(seed))

def Seeds(link,cmd):
  identity=link.identity()
  try:
    sh = GetServerSeedHash(link,'dice')
    ps = GetPlayerSeed(link,'dice')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  link.send('Your server seed hash is %s' % str(sh))
  if ps == "":
    link.send('You have not set a player seed')
  else:
    link.send('Your player seed hash is %s' % str(ps))

def Fair(link,cmd):
  link.send_private("%s's dice betting is provably fair" % config.tipbot_name)
  link.send_private("Your rolls are determined by three pieces of information:")
  link.send_private(" - your server seed. You can see its hash with !seeds")
  link.send_private(" - your player seed. Empty by default, you can set it with !playerseed")
  link.send_private(" - the roll number, displayed with each bet you make")
  link.send_private("To verify past rolls were fair, use !faircheck")
  link.send_private("You will be given your server seed, and a new one will be generated")
  link.send_private("for future rolls. Then follow these steps:")
  link.send_private("Calculate the SHA-256 sum of serverseed:playerseed:rollnumber")
  link.send_private("Take the first 8 characters of this sum to make an hexadecimal")
  link.send_private("number, and divide it by 0xffffffff. You will end up with a number")
  link.send_private("between 0 and 1 which was your roll for that particular bet")
  link.send_private("See !faircode for Python code implementing this check")

def FairCode(link,cmd):
  link.send_private("This Python 2 code takes the seeds and roll number and outputs the roll")
  link.send_private("for the corresponding game. Run it with three arguments: server seed,")
  link.send_private("player seed (use '' if you did not set any), and roll number.")

  link.send_private("import sys,hashlib,random")
  link.send_private("try:")
  link.send_private("  s=hashlib.sha256(sys.argv[1]+':'+sys.argv[2]+':'+sys.argv[3]).hexdigest()")
  link.send_private("  roll = float(long(s[0:8],base=16))/0xffffffff")
  link.send_private("  print '%.16g' % roll")
  link.send_private("except:")
  link.send_private("  print 'need serverseed, playerseed, and roll number'")

def DiceHelp(link):
  link.send_private("The dice module is a provably fair %s dice betting game" % coinspecs.name)
  link.send_private("Basic usage: !dice <amount> <multiplier> [over|under]")
  link.send_private("The goal is to get a roll under (or over, at your option) a target that depends")
  link.send_private("on your chosen profit multiplier (1 for even money)")
  link.send_private("See !fair and !faircode for a description of the provable fairness of the game")
  link.send_private("See !faircheck to get the server seed to check past rolls were fair")



random.seed(time.time())
RegisterModule({
  'name': __name__,
  'help': DiceHelp,
})
RegisterCommand({
  'module': __name__,
  'name': 'dice',
  'parms': '<amount-in-%s> <multiplier> [over|under]' % coinspecs.name,
  'function': Dice,
  'registered': True,
  'help': "play a dice game - house edge %.1f%%" % (float(config.dice_edge)*100)
})
RegisterCommand({
  'module': __name__,
  'name': 'stats',
  'parms': '[<name>]',
  'function': GetDiceStats,
  'registered': True,
  'help': "displays your dice stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'resetstats',
  'parms': '[<name>]',
  'function': ResetDiceStats,
  'registered': True,
  'help': "resets your dice stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'playerseed',
  'parms': '<string>',
  'function': PlayerSeed,
  'registered': True,
  'help': "set a custom seed to use in the hash calculation"
})
RegisterCommand({
  'module': __name__,
  'name': 'seeds',
  'function': Seeds,
  'registered': True,
  'help': "Show hash of your current server seed and your player seed"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircheck',
  'function': FairCheck,
  'registered': True,
  'help': "Check provably fair rolls"
})
RegisterCommand({
  'module': __name__,
  'name': 'fair',
  'function': Fair,
  'help': "describe the provably fair dice game"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircode',
  'function': FairCode,
  'help': "Show sample Python code to check bet fairness"
})
