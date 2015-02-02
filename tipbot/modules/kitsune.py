#!/bin/python
#
# Cryptonote tipbot - kitsune bakuchi
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
from tipbot.command_manager import *
from tipbot.redisdb import *
from tipbot.betutils import *

def Roll(link):
  identity=link.identity()
  try:
    if redis_hexists('kitsune:rolls',identity):
      rolls = redis_hget('kitsune:rolls',identity)
      rolls = long(rolls) + 1
    else:
      rolls = 1
  except Exception,e:
    log_error('Failed to prepare roll for %s: %s' % (identity, str(e)))
    raise

  try:
    log_log('0')
    s = GetServerSeed(link,'kitsune') + ":" + GetPlayerSeed(link,'kitsune') + ":" + str(rolls)
    log_log('1')
    sh = hashlib.sha256(s).hexdigest()
    log_log('2')
    triplet = [ long(sh[0:3],base=16)%6+1, long(sh[3:6],base=16)%6+1, long(sh[6:9],base=16)%6+1 ]
    log_log('3')
    return rolls, triplet
  except Exception,e:
    log_error('Failed to roll for %s: %s' % (identity,str(e)))
    raise

def Kitsune(link,cmd):
  identity=link.identity()
  try:
    amount=float(cmd[1])
    units=StringToUnits(cmd[1])
  except Exception,e:
    link.send("Usage: !kitsune amount")
    return

  log_info("Kitsune: %s wants to bet %s" % (identity, AmountToString(units)))
  potential_loss = amount * 35
  valid,reason = IsBetValid(link,amount,config.kitsune_min_bet,config.kitsune_max_bet,potential_loss,config.kitsune_max_loss,config.kitsune_max_loss_ratio)
  if not valid:
    log_info("Kitsune: %s's bet refused: %s" % (identity, reason))
    link.send("%s: %s" % (link.user.nick, reason))
    return

  try:
    rolls, triplet  = Roll(link)
  except:
    link.send("An error occured")
    return

  lose_units = units
  win_units = long(units * 35) - lose_units
  win = triplet[0] == triplet[1] and triplet[0] == triplet[2]
  if win:
    msg = "%s bets %s and wins %s on roll #%d! %s %s %s" % (link.user.nick, AmountToString(lose_units), AmountToString(win_units+lose_units), rolls, triplet[0], triplet[1], triplet[2])
  else:
    msg = "%s bets %s and loses on roll #%d: %s %s %s" % (link.user.nick, AmountToString(lose_units), rolls, triplet[0], triplet[1], triplet[2])

  try:
    RecordGameResult(link,"kitsune",win,not win,win_units if win else lose_units)
  except:
    return

  redis_hset("kitsune:rolls",identity,rolls)

  link.send("%s" % msg)

def ShowKitsuneStats(link,sidentity,title):
  return ShowGameStats(link,sidentity,title,"kitsune")

def GetKitsuneStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see kitsune stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  ShowKitsuneStats(link,sidentity,NickFromIdentity(sidentity))
  ShowKitsuneStats(link,"reset:"+sidentity,'%s since reset' % NickFromIdentity(sidentity))
  ShowKitsuneStats(link,'','overall')

def ResetKitsuneStats(link,cmd):
  identity=link.identity()
  sidentity = GetParam(cmd,1)
  if sidentity:
    sidentity=IdentityFromString(link,sidentity)
  if sidentity and sidentity != identity:
    if not IsAdmin(link):
      log_error('%s is not admin, cannot see kitsune stats for %s' % (identity, sidentity))
      link.send('Access denied')
      return
  else:
    sidentity=identity
  try:
    ResetGameStats(link,sidentity,"kitsune")
  except Exception,e:
    link.send("An error occured")

def PlayerSeed(link,cmd):
  identity=link.identity()
  fair_string = GetParam(cmd,1)
  if not fair_string:
    link.send("Usage: !playerseed <string>")
    return
  try:
    SetPlayerSeed(link,'kitsune',fair_string)
  except Exception,e:
    log_error('Failed to save player seed for %s: %s' % (identity, str(e)))
    link.send('An error occured')
  try:
    ps = GetPlayerSeed(link,'kitsune')
  except Exception,e:
    log_error('Failed to retrieve newly set player seed for %s: %s' % (identity, str(e)))
    link.send('An error occured')
    return
  link.send('Your new player seed is: %s' % ps)

def FairCheck(link,cmd):
  identity=link.identity()
  try:
    seed = GetServerSeed(link,'kitsune')
  except Exception,e:
    log_error('Failed to get server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  try:
    GenerateServerSeed(link,'kitsune')
  except Exception,e:
    log_error('Failed to generate server seed for %s: %s' % (identity,str(e)))
    link.send('An error has occured')
    return
  link.send('Your server seed was %s - it has now been reset; see !fair for details' % str(seed))

def Seeds(link,cmd):
  identity=link.identity()
  try:
    sh = GetServerSeedHash(link,'kitsune')
    ps = GetPlayerSeed(link,'kitsune')
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
  link.send_private("%s's kitsune betting is provably fair" % config.tipbot_name)
  link.send_private("Your rolls are determined by three pieces of information:")
  link.send_private(" - your server seed. You can see its hash with !seeds")
  link.send_private(" - your player seed. Empty by default, you can set it with !playerseed")
  link.send_private(" - the roll number, displayed with each bet you make")
  link.send_private("To verify past rolls were fair, use !faircheck")
  link.send_private("You will be given your server seed, and a new one will be generated")
  link.send_private("for future rolls. Then follow these steps:")
  link.send_private("Calculate the SHA-256 sum of serverseed:playerseed:rollnumber")
  link.send_private("Use the first 3 digits of the hexadecimal representation of this hash")
  link.send_private("modulo 6 and add 1 to make your first roll. Do the same with the three")
  link.send_private("next digits for the second, and again for the third roll")
  link.send_private("See !faircode for Python code implementing this check")

def FairCode(link,cmd):
  link.send_private("This Python 2 code takes the seeds and roll number and outputs the rolls")
  link.send_private("for the corresponding game. Run it with three arguments: server seed,")
  link.send_private("player seed (use '' if you did not set any), and roll number.")

  link.send_private("import sys,hashlib,random")
  link.send_private("try:")
  link.send_private("  s=hashlib.sha256(sys.argv[1]+':'+sys.argv[2]+':'+sys.argv[3]).hexdigest()")
  link.send_private("  triplet = [ long(s[0:3],base=16)%6+1, long(s[3:6],base=16)%6+1, long(s[6:9],base=16)%6+1 ]")
  link.send_private("  print triplet[0], triplet[1], triplet[2]")
  link.send_private("except:")
  link.send_private("  print 'need serverseed, playerseed, and roll number'")

def KitsuneHelp(link):
  link.send_private("The kitsune module is a provably fair %s dice betting game" % coinspecs.name)
  link.send_private("Basic usage: !kitsune <amount>")
  link.send_private("The goal in the old Japanese game Kitsune Bakuchi is to roll")
  link.send_private("three dice and get three of a kind to win back 35 times your bet")
  link.send_private("See !fair and !faircode for a description of the provable fairness of the game")
  link.send_private("See !faircheck to get the server seed to check past rolls were fair")



random.seed(time.time())
RegisterModule({
  'name': __name__,
  'help': KitsuneHelp,
})
RegisterCommand({
  'module': __name__,
  'name': 'kitsune',
  'parms': '<amount-in-%s>' % coinspecs.name,
  'function': Kitsune,
  'registered': True,
  'help': "play a kitsune bakuchi game - pays 1:35"
})
RegisterCommand({
  'module': __name__,
  'name': 'stats',
  'parms': '[<name>]',
  'function': GetKitsuneStats,
  'registered': True,
  'help': "displays your kitsune bakuchi stats"
})
RegisterCommand({
  'module': __name__,
  'name': 'resetstats',
  'parms': '[<name>]',
  'function': ResetKitsuneStats,
  'registered': True,
  'help': "resets your kitsune bakuchi stats"
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
  'help': "describe the provably fair kitsune bakuchi game"
})
RegisterCommand({
  'module': __name__,
  'name': 'faircode',
  'function': FairCode,
  'help': "Show sample Python code to check bet fairness"
})
