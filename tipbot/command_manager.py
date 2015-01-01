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
from tipbot.utils import *
from tipbot.ircutils import *

commands = dict()
calltable=dict()
idles = []
cleanup = dict()
helps = dict()

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

  module_name = GetParam(cmd,1)

  if module_name:
    SendTo(nick, "Commands for %s's %s module:" % (config.tipbot_name,module_name))
  else:
    SendTo(nick, "Commands for %s (!commands <modulename> for command help):" % config.tipbot_name)

  msgs = dict()
  for command_name in commands:
    c = commands[command_name]
    if 'admin' in c and c['admin'] and not all:
      continue
    module = c['module']
    if module_name:
      if module_name != module:
        continue
      synopsis = c['name']
      if 'parms' in c:
        synopsis = synopsis + " " + c['parms']
      SendTo(nick, "%s - %s" % (synopsis, c['help']))
    else:
      if module in msgs:
        msgs[module] = msgs[module] +(", ")
      else:
        msgs[module] = module + " module: "
      msgs[module] = msgs[module] +(c['name'])

  if not module_name:
    for msg in msgs:
      SendTo(nick, "%s" % msgs[msg])

def RegisterCommand(command):
  commands[command['name']] = command

def RegisterIdleFunction(module,function):
  idles.append((module,function))

def RegisterCleanupFunction(module,function):
  cleanup.append((module,function))

def RegisterHelpFunction(module,function):
  helps[module]=function

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
      f[1](param)
    except Exception,e:
      log_error("Exception running idle function %s from module %s: %s" % (str(f[1]),str(f[2]),str(e)))

def RunHelpFunctions(param):
  for f in helps:
    try:
      helps[f](param)
    except Exception,e:
      log_error("Exception running help function %s from module %s: %s" % (str(helps[f]),str(f),str(e)))

def UnregisterCommands(module):
  global commands
  global idles
  global helps

  if module in cleanup:
    cleanup[module]()
    del cleanup[module]

  new_idles = []
  for f in idles:
    if f[0] != module:
      new_idles.append(f)
  idles = new_idles

  if module in helps:
    del helps[module]

  new_commands = dict()
  for cmd in commands:
    c = commands[cmd]
    if c['module'] != module:
      new_commands[cmd] = c
  commands = new_commands

