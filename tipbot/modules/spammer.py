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

def Ban(link):
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
    cmd="MODE " + chan + " -b " + link.user.ident
    net._irc_sendmsg(cmd)
  except:
    pass

def OnUserJoined(event,*args,**kwargs):
  link=kwargs['link']

  nick=link.user.nick.lower()
  if nick=="lbft" or nick=="lbft_":
    Ban(link)

def OnMessage(event,*args,**kwargs):
  line=kwargs['message']
  if not line:
    return

  line=re.sub(r'\x03[0-9]?[0-9]?','',line)
  line=re.sub(r'\x0f','',line)
  line=line.lower().strip()

  log_info("Testing: " + line)
  for expr in ["astounding!", "triple your btc!", "pm me to begin!", "hatt uu"]:
    if re.match(expr+".*",line):
      link=kwargs['link']
      Ban(link)
      return

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
