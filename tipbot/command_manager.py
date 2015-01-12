#!/bin/python
#
# Cryptonote tipbot - commands
# Copyright 2014,2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import tipbot.config as config
from tipbot.utils import *
from tipbot.ircutils import *

modules = dict()
commands = dict()
calltable=dict()
idles = []
cleanup = dict()

def SendToProxy(nick,chan,msg):
  SendTo(GetSendTo(nick,chan),msg)

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
    SendTo(nick, "Commands for %s (use !commands <modulename> for help about the module's commands):" % config.tipbot_name)

  msgs = dict()
  for command_name in commands:
    for c in commands[command_name]:
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

def RegisterModule(module):
  if module['name'] in modules:
    log_error('a module named %s is already registered' % module['name'])
    return
  modules[module['name']] = module

def GetModuleNameList(admin):
  if admin:
    all = True
  else:
    all = False

  module_names = []
  for command_name in commands:
    for c in commands[command_name]:
      if 'admin' in c and c['admin'] and not all:
        continue
      module = c['module']
      if not module in module_names:
        module_names.append(module)
  return module_names

def RegisterCommand(command):
  if command['name'] in commands:
    log_warn('module %s redefined function %s from module %s' % (command['module'],command['name'],commands[command['name']][0]['module']))
  else:
    commands[command['name']] = []
  commands[command['name']].append(command)

def RegisterIdleFunction(module,function):
  idles.append((module,function))

def RegisterCleanupFunction(module,function):
  cleanup.append((module,function))

def OnCommand(cmd,chan,who,check_admin,check_registered):
  cmdparts = cmd[0].split(':')
  log_log('cmdparts: %s' % str(cmdparts))
  if len(cmdparts) == 2:
    modulename = cmdparts[0]
    cmdname = cmdparts[1]
  elif len(cmdparts) == 1:
    modulename = None
    cmdname = cmdparts[0]
  else:
    SendTo(GetNick(who), "Invalid command, try !help")
    return
  log_log('modulename: %s, cmdname: %s' % (str(modulename),str(cmdname)))
  if cmdname in commands:
    log_log('%s found in commands' % (str(cmd[0])))
    if len(commands[cmdname]) > 1:
      if not modulename:
        msg = ""
        for c in commands[cmdname]:
          if msg != "":
            msg = msg + ", "
          msg = msg + c['module'] + ":" + cmd[0]
        SendTo(GetNick(who), "Ambiguous command, try one of: %s" % msg)
        return
      c = None
      for command in commands[cmdname]:
        if command['module'] == modulename:
          c = command
          break
      if not c:
        SendTo(GetNick(who), "Invalid command, try !help")
        return
    else:
      c = commands[cmdname][0]
    if 'admin' in c and c['admin']:
      check_admin(GetNick(who),chan,c['function'],cmd,SendToProxy,"You must be admin")
    elif 'registered' in c and c['registered']:
      check_registered(GetNick(who),chan,c['function'],cmd,SendToProxy,"You must be registered with Freenode")
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

def RunModuleHelpFunction(module,nick,chan):
  if module in modules:
    try:
      modules[module]['help'](nick,chan)
    except Exception,e:
      log_error("Exception running help function %s from module %s: %s" % (str(modules[module]['help']),str(module),str(e)))
  else:
    SendTo(nick,'No help found for module %s' % module)

def UnregisterModule(module):
  global commands
  global idles

  if module in cleanup:
    cleanup[module]()
    del cleanup[module]

  if module in modules:
    del modules[module]

  new_idles = []
  for f in idles:
    if f[0] != module:
      new_idles.append(f)
  idles = new_idles

  new_commands = dict()
  for cmd in commands:
    newlist = []
    for c in commands[cmd]:
      if c['module'] != module:
        newlist.append(c)
    if len(newlist) > 0:
      new_commands[cmd] = newlist
  commands = new_commands

