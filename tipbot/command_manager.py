#!/bin/python
#
# Cryptonote tipbot - commands
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import tipbot.config as config
from tipbot.irc import *

commands = dict()
calltable=dict()
idles = []

def RunRegisteredCommand(nick,chan,ifyes,yesdata,ifno,nodata):
  if nick not in calltable:
    calltable[nick] = []
  calltable[nick].append([chan,ifyes,yesdata,ifno,nodata])
  if nick in registered_users:
    RunNextCommand(nick,True)
  else:
    SendTo('nickserv', "ACC " + nick)

def IsAdmin(nick):
  return nick in config.admins

def RunAdminCommand(nick,chan,ifyes,yesdata,ifno,nodata):
  if not IsAdmin(nick):
    log_warn('RunAdminCommand: nick %s is not admin, cannot call %s with %s' % (str(nick),str(ifyes),str(yesdata)))
    SendTo(nick, "Access denied")
    return
  RunRegisteredCommand(nick,chan,ifyes,yesdata,ifno,nodata)

def RunNextCommand(nick,registered):
  if registered:
    registered_users.add(nick)
  else:
    registered_users.discard(nick)
  if nick not in calltable:
    log_error( 'Nothing in queue for %s' % nick)
    return
  try:
    if registered:
      calltable[nick][0][1](nick,calltable[nick][0][0],calltable[nick][0][2])
    else:
      calltable[nick][0][3](nick,calltable[nick][0][0],calltable[nick][0][4])
    del calltable[nick][0]
  except Exception, e:
    log_error('RunNextCommand: Exception in action, continuing: %s' % str(e))
    del calltable[nick][0]

def Commands(nick,chan,cmd):
  if IsAdmin(nick):
    all = True
  else:
    all = False
  SendTo(nick, "Commands for %s:" % config.tipbot_name)
  for command_name in commands:
    c = commands[command_name]
    if 'admin' in c and c['admin'] and not all:
      continue
    synopsis = c['name']
    if 'parms' in c:
      synopsis = synopsis + " " + c['parms']
    SendTo(nick, "%s - %s" % (synopsis, c['help']))

def RegisterCommand(command):
  commands[command['name']] = command

def RegisterIdleFunction(function):
  idles.append(function)

def OnCommand(cmd,chan,who,check_admin,check_registered):
  if cmd[0] in commands:
    c = commands[cmd[0]]
    if 'admin' in c and c['admin']:
      check_admin(GetNick(who),chan,c['function'],cmd,SendTo,"You must be admin")
    elif 'registered' in c and c['registered']:
      check_registered(GetNick(who),chan,c['function'],cmd,SendTo,"You must be registered with Freenode")
    else:
      c['function'](GetNick(who),chan,cmd)
  else:
    SendTo(GetNick(who), "Invalid command, try !help")

def RunIdleFunctions(param):
  for f in idles:
    try:
      f(param)
    except Exception,e:
      log_error("Exception running idle function %s: %s" % (str(f),str(e)))


