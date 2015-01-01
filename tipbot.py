#!/bin/python
#
# Cryptonote tipbot
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import os
import socket
import select
import random
import redis
import hashlib
import json
import httplib
import time
import string
import importlib
import tipbot.coinspecs as coinspecs
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.utils import *
from tipbot.ircutils import *
from tipbot.redisdb import *
from tipbot.command_manager import *

selected_coin = None
modulenames = []
argc = 1
while argc < len(sys.argv):
  arg = sys.argv[argc]
  if arg == "-c" or arg == "--coin":
    if argc+1 == len(sys.argv):
      log_error('Usage: tipbot.py [-h|--help] [-m|--module modulename]* -c|--coin <coinname>')
      exit(1)
    argc = argc+1
    selected_coin = sys.argv[argc]
    try:
      log_info('Importing %s coin setup' % selected_coin)
      if not selected_coin in coinspecs.coinspecs:
        log_error('Unknown coin: %s' % selected_coin)
        exit(1)
      for field in coinspecs.coinspecs[selected_coin]:
        setattr(coinspecs, field, coinspecs.coinspecs[selected_coin][field])
    except Exception,e:
      log_error('Failed to load coin setup for %s: %s' % (selected_coin, str(e)))
      exit(1)
  elif arg == "-m" or arg == "--module":
    if argc+1 == len(sys.argv):
      log_error('Usage: tipbot.py [-m|--module modulename]* -c|--coin <coinname>')
      exit(1)
    argc = argc+1
    modulenames.append(sys.argv[argc])
  elif arg == "-h" or arg == "--help":
    log_info('Usage: tipbot.py [-m|--module modulename]* -c|--coin <coinname>')
    exit(0)
  else:
    log_error('Usage: tipbot.py [-m|--module modulename]* -c|--coin <coinname>')
    exit(1)
  argc = argc + 1

if not selected_coin:
  log_error('Coin setup needs to be specified with -c. See --help')
  exit(1)

sys.path.append(os.path.join('tipbot','modules'))
for modulename in modulenames:
  log_info('Importing %s module' % modulename)
  try:
    __import__(modulename)
  except Exception,e:
    log_error('Failed to load module "%s": %s' % (modulename, str(e)))
    exit(1)



def GetBalance(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  log_log("GetBalance: checking %s" % nick)
  try:
    balance = redis_hget("balances",nick)
    if balance == None:
      balance = 0
    sbalance = AmountToString(balance)
    SendTo(sendto, "%s's balance is %s" % (nick, sbalance))
  except Exception, e:
    log_error('GetBalance: exception: %s' % str(e))
    SendTo(sendto, "An error has occured")

def AddBalance(nick,chan,cmd):
  amount=cmd[1]
  log_info("AddBalance: Adding %s to %s's balance" % (AmountToString(amount),nick))
  try:
    balance = redis_hincrby("balances",nick,amount)
  except Exception, e:
    log_error('AddBalance: exception: %s' % str(e))
    SendTo(nick, "An error has occured")

def ScanWho(nick,chan,cmd):
  Who(chan)

def GetHeight(nick,chan,cmd):
  log_info('GetHeight: %s wants to know block height' % nick)
  try:
    j = SendDaemonHTMLCommand("getheight")
  except Exception,e:
    log_error('GetHeight: error: %s' % str(e))
    SendTo(nick,"An error has occured")
    return
  log_log('GetHeight: Got reply: %s' % str(j))
  if not "height" in j:
    log_error('GetHeight: Cannot see height in here')
    SendTo(nick, "Height not found")
    return
  height=j["height"]
  log_info('GetHeight: height is %s' % str(height))
  SendTo(nick, "Height: %s" % str(height))

def GetTipbotBalance(nick,chan,cmd):
  log_info('%s wants to know the tipbot balance' % nick)
  try:
    j = SendWalletJSONRPCCommand("getbalance",None)
  except Exception,e:
    SendTo(nick,"An error has occured")
    return
  if not "result" in j:
    log_error('GetTipbotBalance: result not found in reply')
    SendTo(nick, "An error has occured")
    return
  result = j["result"]
  if not "balance" in result:
    log_error('GetTipbotBalance: balance not found in result')
    SendTo(nick, "An error has occured")
    return
  if not "unlocked_balance" in result:
    log_error('GetTipbotBalance: unlocked_balance not found in result')
    SendTo(nick, "An error has occured")
    return
  balance = result["balance"]
  unlocked_balance = result["unlocked_balance"]
  log_log('GetTipbotBalance: balance: %s' % str(balance))
  log_log('GetTipbotBalance: unlocked_balance: %s' % str(unlocked_balance))
  pending = long(balance)-long(unlocked_balance)
  if pending < 0:
    log_error('GetTipbotBalance: Negative pending balance! balance %s, unlocked %s' % (str(balance),str(unlocked)))
    SendTo(nick, "An error has occured")
    return
  if pending == 0:
    log_info("GetTipbotBalance: Tipbot balance: %s" % AmountToString(balance))
    SendTo(nick,"Tipbot balance: %s" % AmountToString(balance))
  else:
    log_info("GetTipbotBalance: Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))
    SendTo(nick,"Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))

def DumpUsers(nick,chan,cmd):
  userstable = GetUsersTable()
  log_info(str(userstable))

def Help(nick,chan,cmd):
  SendTo(nick, "See available commands with !commands or !commands <modulename>")
  RunHelpFunctions(nick)
  if coinspecs.web_wallet_url:
    SendTo(nick, "No %s address ? You can use %s" % (coinspecs.name, coinspecs.web_wallet_url))

def Info(nick,chan,cmd):
  SendTo(nick, "Info for %s:" % config.tipbot_name)
  SendTo(nick, "Copyright 2014 moneromooo - http://duckpool.mooo.com/tipbot/")
  SendTo(nick, "Type !help, or !commands for a list of commands")
  SendTo(nick, "NO WARRANTY, YOU MAY LOSE YOUR COINS")
  SendTo(nick, "By sending your %s to %s, you are giving up their control" % (coinspecs.name, config.tipbot_name))
  SendTo(nick, "to whoever runs the tipbot. Any tip you make/receive using %s" % config.tipbot_name)
  SendTo(nick, "is obviously not anonymous. %s's wallet may end up corrupt, or be" % config.tipbot_name)
  SendTo(nick, "stolen, the server compromised, etc. While I hope this won't be the case,")
  SendTo(nick, "I will not offer any warranty whatsoever for the use of %s or the" % config.tipbot_name)
  SendTo(nick, "return of any %s. Use at your own risk." % coinspecs.name)
  SendTo(nick, "That being said, I hope you enjoy using it :)")

def InitScanBlockHeight():
  try:
    scan_block_height = redis_get("scan_block_height")
    scan_block_height = long(scan_block_height)
  except Exception,e:
    try:
      redis_set("scan_block_height",0)
    except Exception,e:
      log_error('Failed to initialize scan_block_height: %s' % str(e))

def ShowActivity(nick,chan,cmd):
  achan=cmd[1]
  anick=cmd[2]
  activity = GetTimeSinceActive(achan,anick)
  if activity:
    SendTo(nick,"%s was active in %s %f seconds ago" % (anick,achan,activity))
  else:
    SendTo(nick,"%s was never active in %s" % (anick,achan))

def SendToNick(nick,chan,msg):
  SendTo(nick,msg)

def IsRegistered(nick,chan,cmd):
  RunRegisteredCommand(nick,chan,SendToNick,"You are registered",SendToNick,"You are not registered")

def Reload(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  modulename=GetParam(cmd,1)
  if not modulename:
    SendTo(sendto,"Usage: reload <modulename>")
    return
  if modulename=="builtin":
    SendTo(sendto,"Cannot reload builtin module")
    return
  log_info('Unloading %s module' % modulename)
  UnregisterCommands(modulename)
  log_info('Reloading %s module' % modulename)
  try:
    reload(sys.modules[modulename])
    SendTo(sendto,'%s reloaded' % modulename)
  except Exception,e:
    log_error('Failed to load module "%s": %s' % (modulename, str(e)))
    SendTo(sendto,'An error occured')

def OnIdle():
  RunIdleFunctions([irc,redisdb])

def OnIdentified(nick, identified):
  RunNextCommand(nick, identified)

def RegisterCommands():
  RegisterCommand({'module': 'builtin', 'name': 'help', 'function': Help, 'help': "Displays help about %s" % config.tipbot_name})
  RegisterCommand({'module': 'builtin', 'name': 'commands', 'parms': '[module]', 'function': Commands, 'help': "Displays list of commands"})
  RegisterCommand({'module': 'builtin', 'name': 'isregistered', 'function': IsRegistered, 'help': "show whether you are currently registered with freenode"})
  RegisterCommand({'module': 'builtin', 'name': 'balance', 'function': GetBalance, 'registered': True, 'help': "show your current balance"})
  RegisterCommand({'module': 'builtin', 'name': 'info', 'function': Info, 'help': "infornmation about %s" % config.tipbot_name})

  RegisterCommand({'module': 'builtin', 'name': 'height', 'function': GetHeight, 'admin': True, 'help': "Get current blockchain height"})
  RegisterCommand({'module': 'builtin', 'name': 'tipbot_balance', 'function': GetTipbotBalance, 'admin': True, 'help': "Get current blockchain height"})
  RegisterCommand({'module': 'builtin', 'name': 'addbalance', 'function': AddBalance, 'admin': True, 'help': "Add balance to your account"})
  RegisterCommand({'module': 'builtin', 'name': 'scanwho', 'function': ScanWho, 'admin': True, 'help': "Refresh users list in a channel"})
  RegisterCommand({'module': 'builtin', 'name': 'dump_users', 'function': DumpUsers, 'admin': True, 'help': "Dump users table to log"})
  RegisterCommand({'module': 'builtin', 'name': 'show_activity', 'function': ShowActivity, 'admin': True, 'help': "Show time since a user was last active"})
  RegisterCommand({'module': 'builtin', 'name': 'reload', 'function': Reload, 'admin': True, 'help': "Reload a module"})

def OnCommandProxy(cmd,chan,who):
  OnCommand(cmd,chan,who,RunAdminCommand,RunRegisteredCommand)


redisdb = connect_to_redis(config.redis_host,config.redis_port)
irc = connect_to_irc(config.irc_network,config.irc_port,config.tipbot_name,GetPassword(),config.irc_send_delay)
InitScanBlockHeight()
RegisterCommands()

IRCLoop(OnIdle,OnIdentified,OnCommandProxy)
