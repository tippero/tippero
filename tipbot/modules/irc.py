#!/bin/python
#
# Cryptonote tipbot - IRC commands
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import string
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.utils import *
from tipbot.irc import *
from tipbot.command_manager import *

def JoinChannel(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  jchan = GetParam(cmd,1)
  if not jchan:
    SendTo(sendto,'Usage: join <channel>')
    rerurn
  if jchan[0] != '#':
    SendTo(sendto,'Channel name must start with #')
    return
  Join(jchan)

def PartChannel(nick,chan,cmd):
  sendto=GetSendTo(nick,chan)
  pchan = GetParam(cmd,1)
  if pchan:
    if pchan[0] != '#':
      SendTo(sendto,'Channel name must start with #')
      return
  else:
    pchan = chan
  Part(pchan)

def QuitIRC(nick,chan,cmd):
  msg = ""
  for w in cmd[:1]:
    msg = msg + " " + w
  Quit(msg)

RegisterCommand({
  'module': __name__,
  'name': 'join',
  'parms': '<channel>',
  'function': JoinChannel,
  'admin': True,
  'help': "Makes %s join a channel" % (config.tipbot_name)
})
RegisterCommand({
  'module': __name__,
  'name': 'part',
  'parms': '<channel>',
  'function': PartChannel,
  'admin': True,
  'help': "Makes %s part from a channel" % (config.tipbot_name)
})
RegisterCommand({
  'module': __name__,
  'name': 'quit',
  'function': QuitIRC,
  'admin': True,
  'help': "Makes %s quit IRC" % (config.tipbot_name)
})
