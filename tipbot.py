#!/bin/python
#
# Cryptonote tipbot
# Copyright 2014,2015 moneromooo
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
from tipbot.link import *
from tipbot.user import *
from tipbot.group import *
from tipbot.utils import *
from tipbot.redisdb import *
from tipbot.command_manager import *

disabled = False

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
  if modulename in sys.modules:
    log_error('A %s module already exists' % modulename)
    exit(1)
  log_info('Importing %s module' % modulename)
  try:
    __import__(modulename)
  except Exception,e:
    log_error('Failed to load module "%s": %s' % (modulename, str(e)))
    exit(1)



def GetBalance(link,cmd):
  nick=link.user.nick
  log_log("GetBalance: checking %s (%s)" % (link.identity(),str(link)))
  try:
    balance = redis_hget("balances",link.identity())
    if balance == None:
      balance = 0
    balance = long(balance)
    sbalance = AmountToString(balance)
    if balance < coinspecs.atomic_units:
      if balance == 0:
        link.send("%s's balance is %s" % (nick, sbalance))
      else:
        link.send("%s's balance is %s (%.16g %s)" % (nick, sbalance, float(balance) / coinspecs.atomic_units, coinspecs.name))
    else:
      link.send("%s's balance is %s" % (nick, sbalance))
  except Exception, e:
    log_error('GetBalance: exception: %s' % str(e))
    link.send("An error has occured")

def AddBalance(link,cmd):
  nick=link.user.nick
  if GetParam(cmd,2):
    anick = GetParam(cmd,1)
    amount = GetParam(cmd,2)
  else:
    anick = nick
    amount = GetParam(cmd,1)
  if not amount:
    link.send('usage: !addbalance [<nick>] <amount>')
    return
  try:
    units = long(float(amount)*coinspecs.atomic_units)
  except Exception,e:
    log_error('AddBalance: error converting amount: %s' % str(e))
    link.send('usage: !addbalance [<nick>] <amount>')
    return
  if anick.find(':') == -1:
    network=link.network
    log_info('No network found in %s, using %s from command originator' % (anick,network.name))
    aidentity=Link(network,User(network,anick)).identity()
  else:
    aidentity=anick
  log_info("AddBalance: Adding %s to %s's balance" % (AmountToString(units),aidentity))
  try:
    balance = redis_hincrby("balances",aidentity,units)
  except Exception, e:
    log_error('AddBalance: exception: %s' % str(e))
    link.send( "An error has occured")
  link.send("%s's balance is now %s" % (aidentity,AmountToString(balance)))

def ScanWho(link,cmd):
  link.network.update_users_list(link.group.name if link.group else None)

def GetHeight(link,cmd):
  log_info('GetHeight: %s wants to know block height' % str(link))
  try:
    j = SendDaemonHTMLCommand("getheight")
  except Exception,e:
    log_error('GetHeight: error: %s' % str(e))
    link.send("An error has occured")
    return
  log_log('GetHeight: Got reply: %s' % str(j))
  if not "height" in j:
    log_error('GetHeight: Cannot see height in here')
    link.send("Height not found")
    return
  height=j["height"]
  log_info('GetHeight: height is %s' % str(height))
  link.send("Height: %s" % str(height))

def GetTipbotBalance(link,cmd):
  log_info('%s wants to know the tipbot balance' % str(link))
  try:
    balance, unlocked_balance = RetrieveTipbotBalance()
  except Exception,e:
    link.send("An error has occured")
    return
  pending = long(balance)-long(unlocked_balance)
  if pending == 0:
    log_info("GetTipbotBalance: Tipbot balance: %s" % AmountToString(balance))
    link.send("Tipbot balance: %s" % AmountToString(balance))
  else:
    log_info("GetTipbotBalance: Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))
    link.send("Tipbot balance: %s (%s pending)" % (AmountToString(unlocked_balance), AmountToString(pending)))

def DumpUsers(link,cmd):
  for network in networks:
    network.dump_users()

def Help(link,cmd):
  module = GetParam(cmd,1)
  if module:
    RunModuleHelpFunction(module,link)
    return

  link.send("See available commands with !commands or !commands <modulename>")
  link.send("Available modules: %s" % ", ".join(GetModuleNameList(IsAdmin(link))))
  link.send("Get help on a particular module with !help <modulename>")
  if coinspecs.web_wallet_url:
    link.send("No %s address ? You can use %s" % (coinspecs.name, coinspecs.web_wallet_url))

def Info(link,cmd):
  link.send("Info for %s:" % config.tipbot_name)
  link.send("Copyright 2014,2015 moneromooo - http://duckpool.mooo.com/tipbot/")
  link.send("Type !help, or !commands for a list of commands")
  link.send("NO WARRANTY, YOU MAY LOSE YOUR COINS")
  link.send("By sending your %s to %s, you are giving up their control" % (coinspecs.name, config.tipbot_name))
  link.send("to whoever runs the tipbot. Any tip you make/receive using %s" % config.tipbot_name)
  link.send("is obviously not anonymous. %s's wallet may end up corrupt, or be" % config.tipbot_name)
  link.send("stolen, the server compromised, etc. While I hope this won't be the case,")
  link.send("I will not offer any warranty whatsoever for the use of %s or the" % config.tipbot_name)
  link.send("return of any %s. Use at your own risk." % coinspecs.name)
  link.send("That being said, I hope you enjoy using it :)")

def InitScanBlockHeight():
  try:
    scan_block_height = redis_get("scan_block_height")
    scan_block_height = long(scan_block_height)
  except Exception,e:
    try:
      redis_set("scan_block_height",0)
    except Exception,e:
      log_error('Failed to initialize scan_block_height: %s' % str(e))

def ShowActivity(link,cmd):
  anick=GetParam(cmd,1)
  achan=GetParam(cmd,2)
  if not anick or not achan:
    link.send('usage: !show_activity <nick> <chan>')
    return
  if anick.find(':') == -1:
    network = link.network
  else:
    parts=anick.split(':')
    network_name=parts[0]
    anick=parts[1]
    network = GetNetworkByName(network_name)
  if network:
    last_activity = network.get_last_active_time(anick,achan)
    if last_activity:
      link.send("%s was active in %s %f seconds ago" % (anick,achan,now-last_activity))
    else:
      link.send("%s was never active in %s" % (anick,achan))
  else:
    link.send("%s is not a valid network" % network)

def SendToLink(link,msg):
  link.send(msg)

def IsRegistered(link,cmd):
  RunRegisteredCommand(link,SendToLink,"You are registered",SendToLink,"You are not registered")

def Reload(link,cmd):
  modulename=GetParam(cmd,1)
  if not modulename:
    link.send("Usage: reload <modulename>")
    return
  if modulename=="builtin":
    link.send("Cannot reload builtin module")
    return
  if not modulename in sys.modules:
    link.send("%s is not a dynamic module" % modulename)
    return
  log_info('Unloading %s module' % modulename)
  UnregisterModule(modulename)
  log_info('Reloading %s module' % modulename)
  try:
    reload(sys.modules[modulename])
    link.send('%s reloaded' % modulename)
  except Exception,e:
    log_error('Failed to load module "%s": %s' % (modulename, str(e)))
    link.send('An error occured')

def Disable(link,cmd):
  global disabled
  disabled = True
  link.send('%s disabled, will require restart' % config.tipbot_name)

def OnIdle():
  if disabled:
    return
  RunIdleFunctions([irc,redisdb])

def Quit(link,cmd):
  global networks
  msg = ""
  for w in cmd[1:]:
    msg = msg + " " + w
  for network in networks:
    log_info('Quitting %s network' % network.name)
    network.quit()
  networks = []

def OnIdle():
  RunIdleFunctions()

def OnIdentified(link, identified):
  if disabled:
    log_info('Ignoring identified notification for %s while disabled' % str(link.identity()))
    return
  RunNextCommand(link, identified)

def RegisterCommands():
  RegisterCommand({'module': 'builtin', 'name': 'help', 'parms': '[module]', 'function': Help, 'help': "Displays help about %s" % config.tipbot_name})
  RegisterCommand({'module': 'builtin', 'name': 'commands', 'parms': '[module]', 'function': Commands, 'help': "Displays list of commands"})
  RegisterCommand({'module': 'builtin', 'name': 'isregistered', 'function': IsRegistered, 'help': "show whether you are currently registered with freenode"})
  RegisterCommand({'module': 'builtin', 'name': 'balance', 'function': GetBalance, 'registered': True, 'help': "show your current balance"})
  RegisterCommand({'module': 'builtin', 'name': 'info', 'function': Info, 'help': "infornmation about %s" % config.tipbot_name})

  RegisterCommand({'module': 'builtin', 'name': 'height', 'function': GetHeight, 'admin': True, 'help': "Get current blockchain height"})
  RegisterCommand({'module': 'builtin', 'name': 'tipbot_balance', 'function': GetTipbotBalance, 'admin': True, 'help': "Get current blockchain height"})
  RegisterCommand({'module': 'builtin', 'name': 'addbalance', 'parms': '<nick> <amount>', 'function': AddBalance, 'admin': True, 'help': "Add balance to your account"})
  RegisterCommand({'module': 'builtin', 'name': 'scanwho', 'function': ScanWho, 'admin': True, 'help': "Refresh users list in a channel"})
  RegisterCommand({'module': 'builtin', 'name': 'dump_users', 'function': DumpUsers, 'admin': True, 'help': "Dump users table to log"})
  RegisterCommand({'module': 'builtin', 'name': 'show_activity', 'function': ShowActivity, 'admin': True, 'help': "Show time since a user was last active"})
  RegisterCommand({'module': 'builtin', 'name': 'reload', 'function': Reload, 'admin': True, 'help': "Reload a module"})
  RegisterCommand({'module': 'builtin', 'name': 'disable', 'function': Disable, 'admin': True, 'help': "Disable %s"%config.tipbot_name})
  RegisterCommand({'module': 'builtin', 'name': 'quit', 'function': Quit, 'admin': True, 'help': "Quit"})

def OnCommandProxy(link,cmd):
  if disabled:
    log_info('Ignoring command from %s while disabled: %s' % (str(link.identity()),str(cmd)))
    return
  link.batch_send_start()
  try:
    OnCommand(link,cmd,RunAdminCommand,RunRegisteredCommand)
  except Exception,e:
    log_error('Exception running command %s: %s' % (str(cmd),str(e)))
  link.batch_send_done()

def MigrateBalances():
  balances=redis_hgetall('balances')
  for balance in balances:
    if balance.find(':') == -1:
      redis_hset('balances','freenode:'+balance,balances[balance])
      redis_hdel('balances',balance)

RegisterCommands()
redisdb = connect_to_redis(config.redis_host,config.redis_port)
MigrateBalances()
InitScanBlockHeight()

# TODO: make this be created when the module is loaded
irc = sys.modules["freenode"].FreenodeNetwork()
irc.set_callbacks(OnCommandProxy,OnIdentified)
if irc.connect(config.irc_network,config.irc_port,config.tipbot_name,GetPassword(),config.irc_send_delay):
  AddNetwork(irc)

while len(networks)>0:
  for network in networks:
    network.update()

  OnIdle()


log_info('shutting down redis')
redisdb.shutdown
log_info('exiting')
