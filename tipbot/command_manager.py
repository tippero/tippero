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

import time
import tipbot.config as config
from tipbot.utils import *

modules = dict()
commands = dict()
event_handlers = dict()
calltable=dict()

def SendToProxy(link,msg):
  link.send(msg)

def RunRegisteredCommand(link,ifyes,yesdata,ifno,nodata):
  if link.identity() not in calltable:
    calltable[link.identity()] = []
  calltable[link.identity()].append([link,ifyes,yesdata,ifno,nodata,time.time()+20])
  if link.network.is_identified(link):
    RunNextCommand(link,True)
  else:
    link.network.identify(link)

def IsAdmin(link):
  return link.identity() in config.admins

def RunAdminCommand(link,ifyes,yesdata,ifno,nodata):
  if not IsAdmin(link):
    log_warn('RunAdminCommand: %s is not admin, cannot call %s with %s' % (str(link.identity()),str(ifyes),str(yesdata)))
    link.send("Access denied")
    return
  RunRegisteredCommand(link,ifyes,yesdata,ifno,nodata)

def RunNextCommand(link,registered):
  identity = link.identity()
  if identity not in calltable:
    log_error('Nothing in queue for %s' % identity)
    return
  try:
    link=calltable[identity][0][0]
    Lock()
    if registered:
      calltable[identity][0][1](link,calltable[identity][0][2])
    else:
      calltable[identity][0][3](link,calltable[identity][0][4])
    del calltable[identity][0]
  except Exception, e:
    log_error('RunNextCommand: Exception in action, continuing: %s' % str(e))
    del calltable[identity][0]
  finally:
    Unlock()

def PruneOldWaitingCommands():
  Lock()
  now=time.time()
  for identity in calltable.keys():
    while len(calltable[identity])>0 and calltable[identity][0][5]<now:
      link=calltable[identity][0][0]
      log_info('deleting old command: %s, %s' % (str(calltable[identity][0][1]), str(calltable[identity][0][3])))
      link.send("Nickserv didn't reply, gonna have to deny access, mate")
      del calltable[identity][0]
  Unlock()

def Commands(link,cmd):
  if IsAdmin(link):
    all = True
  else:
    all = False

  module_name = GetParam(cmd,1)

  if module_name:
    if not module_name in modules:
      link.send_private("%s is not a module, see module list with !commands" % module_name)
      return
    link.send_private("Commands for %s's %s module:" % (config.tipbot_name,module_name))
  else:
    link.send_private("Commands for %s (use !commands <modulename> for help about the module's commands):" % config.tipbot_name)

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
        link.send_private("%s - %s" % (synopsis, c['help']))
      else:
        if module in msgs:
          msgs[module] = msgs[module] +(", ")
        else:
          msgs[module] = module + " module: "
        msgs[module] = msgs[module] +(c['name'])

  if not module_name:
    for msg in msgs:
      link.send_private("%s" % msgs[msg])

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

def RegisterEventHandler(eh):
  if not eh['event'] in event_handlers:
    event_handlers[eh['event']] = []
  event_handlers[eh['event']].append(eh)

def OnCommand(link,cmd,check_admin,check_registered):
  cmdparts = cmd[0].split(':')
  log_log('cmdparts: %s' % str(cmdparts))
  if len(cmdparts) == 2:
    modulename = cmdparts[0]
    cmdname = cmdparts[1]
  elif len(cmdparts) == 1:
    modulename = None
    cmdname = cmdparts[0]
  else:
    link.send("Invalid command, try !help")
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
        link.send("Ambiguous command, try one of: %s" % msg)
        return
      c = None
      for command in commands[cmdname]:
        if command['module'] == modulename:
          c = command
          break
      if not c:
        link.send("Invalid command, try !help")
        return
    else:
      c = commands[cmdname][0]
    if 'admin' in c and c['admin']:
      check_admin(link,c['function'],cmd,SendToProxy,"You must be admin")
    elif 'registered' in c and c['registered']:
      check_registered(link,c['function'],cmd,SendToProxy,"You must be registered with Freenode, or known for a minute")
    else:
      Lock()
      try:
        c['function'](link,cmd)
      except:
        raise
      finally:
        Unlock()
  else:
    silent = False
    if link.network.name in config.silent_invalid_commands:
      if cmdname in config.silent_invalid_commands[link.network.name]:
        log_info('silently ignoring command %s on %s' % (cmdname,link.network.name))
        silent = True
    if not silent:
      link.send("Invalid command, try !help")

def OnEvent(event,*args,**kwargs):
  log_log('modulename: event %s' % str(event))
  if not event in event_handlers:
    return

  for eh in event_handlers[event]:
    Lock()
    try:
      log_log('Calling %s handler from module %s' % (str(event),eh['module']))
      eh['function'](event,*args,**kwargs)
    except:
      raise
    finally:
      Unlock()

def RunIdleFunctions(param=None):
  for module in modules:
    if 'idle' in modules[module]:
      f=modules[module]['idle']
      try:
        Lock()
        f(param)
      except Exception,e:
        log_error("Exception running idle function %s from module %s: %s" % (str(f),module,str(e)))
      finally:
        Unlock()
  PruneOldWaitingCommands()

def RunModuleHelpFunction(module,link):
  if module in modules:
    try:
      modules[module]['help'](link)
    except Exception,e:
      log_error("Exception running help function %s from module %s: %s" % (str(modules[module]['help']),str(module),str(e)))
  else:
    link.send_private('No help found for module %s' % module)

def UnregisterModule(module):
  global commands
  global event_handlers
  global idles

  if not module in modules:
    log_error('Trying to unregister module %s, which is not registered' % module)
    return

  if 'cleanup' in modules[module]:
    modules[module]['cleanup']()

  new_commands = dict()
  for cmd in commands:
    newlist = []
    for c in commands[cmd]:
      if c['module'] != module:
        newlist.append(c)
    if len(newlist) > 0:
      new_commands[cmd] = newlist
  commands = new_commands

  new_event_handlers = dict()
  for cmd in event_handlers:
    newlist = []
    for c in event_handlers[cmd]:
      if c['module'] != module:
        newlist.append(c)
    if len(newlist) > 0:
      new_event_handlers[cmd] = newlist
  event_handlers = new_event_handlers

  del modules[module]
