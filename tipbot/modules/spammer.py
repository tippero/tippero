#!/bin/python
#
# Cryptonote tipbot - matylda commands
# Copyright 2014, 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import redis
import string
import re
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
import tipbot.coinspecs as coinspecs
from tipbot.utils import *
from tipbot.user import User
from tipbot.link import Link
from tipbot.redisdb import *
from tipbot.command_manager import *

def BanUser(link):
  log_info('Banning %s (%s)' % (link.user.nick, link.user.ident))
  if not link.group:
    return
  chan=link.group.name
  log_info("chan: " + chan)
  net=link.network
  try:
    cmd="MODE " + chan + " +b " + link.user.ident
    net._irc_sendmsg(cmd)
    cmd="KICK " + chan + " " + link.user.nick
    net._irc_sendmsg(cmd)
  except:
    pass

def MuteUser(link):
  log_info('Muting %s (%s)' % (link.user.nick, link.user.ident))
  if not link.group:
    return
  chan=link.group.name
  log_info("chan: " + chan)
  net=link.network
  try:
    cmd="MODE " + chan + " +q " + link.user.ident
    net._irc_sendmsg(cmd)
  except:
    pass

def OnUserJoined(event,*args,**kwargs):
  link=kwargs['link']

  nick=link.user.nick.lower()
  if nick=="lbft" or nick=="lbft_":
    BanUser(link)

triggers=[l.lower() for l in [
    "triple your btc", "pm me to begin", "hatt uu",
    "accelerate the blockchain", "u stappid", "me a message to begin",
    "the ops have confirmed", "expanding technology", "exploding technology",
    "allah is doing", "pm me to get going", "defragment the blockchain to grow"
]]

def OnMessage(event,*args,**kwargs):
  line=kwargs['message']
  if not line:
    return
  link=kwargs['link']
  if IsAdmin(link):
    return
  if link.nick in config.allowed:
    return

  line=re.sub(r'\x03[0-9]?[0-9]?','',line)
  line=re.sub(r'\x0f','',line)
  line=line.lower().strip()

  log_info("Testing: " + line)
  for expr in triggers:
    if re.match(".*"+expr+".*",line):
      MuteUser(link)
      return

def AddTrigger(link,cmd):
  triggers.append(" ".join(cmd[1:]))

def ShowTriggers(link,cmd):
  link.send(", ".join(triggers))

def Ban(link,cmd):
  link.send("disabled") # need to ban by ident
  return

  try:
    who=cmd[1]
  except Exception,e:
    link.send("usage: ban <nick>")
    return
  group=link.group
  if not group:
    link.send("Not in a channel")
    return
  l=Link(link.network,User(link.network,who),group)
  BanUser(l)

def Mute(link,cmd):
  link.send("disabled") # need to mute by ident
  return

  try:
    who=cmd[1]
  except Exception,e:
    link.send("usage: mute <nick>")
    return
  group=link.group
  if not group:
    link.send("Not in a channel")
    return
  l=Link(link.network,User(link.network,who),group)
  MuteUser(l)

def Help(link):
  link.send_private('Ban assholes')


RegisterModule({
  'name': __name__,
  'help': Help,
})
RegisterEventHandler({
  'module': __name__,
  'event': 'user-joined',
  'function': OnUserJoined,
})
RegisterEventHandler({
  'module': __name__,
  'event': 'message',
  'function': OnMessage,
})
RegisterCommand({
  'module': __name__,
  'name': 'add_trigger',
  'function': AddTrigger,
  'admin': True,
  'help': "add keyword trigger to spammer trap"
})
RegisterCommand({
  'module': __name__,
  'name': 'show_triggers',
  'function': ShowTriggers,
  'admin': True,
  'help': "list keyword triggers"
})
RegisterCommand({
  'module': __name__,
  'name': 'ban',
  'function': Ban,
  'admin': True,
  'help': "ban a user"
})
RegisterCommand({
  'module': __name__,
  'name': 'mute',
  'function': Mute,
  'admin': True,
  'help': "mute a user"
})
