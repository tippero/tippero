#!/bin/python
#
# Cryptonote tipbot - IRC routines
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import socket
import ssl
import select
import time
import string
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log, log_IRCSEND, log_IRCRECV

irc_line_delay = 0
irc = None
sslirc = None
irc_password = ""
irc_min_send_delay = 0.01 # seconds
irc_max_send_delay = 5 # seconds

last_ping_time = time.time()
last_send_time = 0
current_send_delay = irc_min_send_delay
irc_network = None
irc_port = None
irc_name = None

userstable=dict()
registered_users=set()

def SendIRC(msg):
  global last_send_time, current_send_delay

  t = time.time()
  dt = t - last_send_time
  if dt < current_send_delay:
    time.sleep (current_send_delay - dt)
    current_send_delay = current_send_delay * 1.5
    if current_send_delay > irc_max_send_delay:
      current_send_delay = irc_max_send_delay
  else:
    current_send_delay = current_send_delay / 1.5
    if current_send_delay < irc_min_send_delay:
      current_send_delay = irc_min_send_delay

  log_IRCSEND(msg)
  irc_send(msg + '\r\n')
  last_send_time = time.time()

def irc_recv(size,flags=None):
  if config.irc_use_ssl:
    return sslirc.read(size)
  else:
    return irc.recv(size,flags)

def irc_send(data):
  if config.irc_use_ssl:
    return sslirc.write(data)
  else:
    return irc.send(data)

def connect_to_irc(network,port,name,password,delay):
  global irc
  global sslirc
  global irc_line_delay
  global irc_network
  global irc_port
  global irc_line_delay
  global irc_password

  irc_network=network
  irc_port=port
  irc_name=name
  irc_line_delay = delay
  irc_password=password
  log_info('Connecting to IRC at %s:%u' % (network, port))
  try:
    irc = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
    if config.irc_use_ssl:
      try:
        raise RuntimeError('')
        irc_ssl_context = ssl.create_default_context()
        sslirc = irc_ssl_context.wrap_socket(irc, network)
        sslirc.connect ( ( network, port ) )
      except Exception,e:
        log_warn('Failed to create SSL context, using fallback code')
        irc.connect ( ( network, port ) )
        sslirc = socket.ssl(irc)
  except Exception, e:
    log_error( 'Error initializing IRC: %s' % str(e))
    exit()
  log_IRCRECV(irc_recv(4096))
  SendIRC ( 'PASS *********')
  SendIRC ( 'NICK %s' % name)
  SendIRC ( 'USER %s %s %s :%s' % (name, name, name, name))
  return irc

def reconnect_to_irc():
  connect_to_irc(irc_network,irc_port,irc_name,irc_password,irc_line_delay)

def Send(msg):
    SendIRC ('PRIVMSG ' + config.irc_homechan + ' : ' + msg)

def SendTo(where,msg):
    SendIRC ('PRIVMSG ' + where + ' : ' + msg)

def Join(chan):
    SendIRC ( 'JOIN ' + chan)

def Part(chan):
    SendIRC ( 'PART ' + chan)

def Who(chan):
    userstable[chan] = dict()
    SendIRC ( 'WHO ' + chan)

def GetHost(host):                            # Return Host
    host = host.split('@')[1]
    host = host.split(' ')[0]
    return host

def GetChannel(data):                        # Return Channel
    channel = data.split('#')[1]
    channel = channel.split(':')[0]
    channel = '#' + channel
    channel = channel.strip(' \t\n\r')
    return channel

def GetNick(data):                            # Return Nickname
    nick = data.split('!')[0]
    nick = nick.replace(':', ' ')
    nick = nick.replace(' ', '')
    nick = nick.strip(' \t\n\r')
    return nick

def GetSendTo(nick,chan):
  if chan[0] == '#':
    return chan
  return nick

def UpdateLastActiveTime(chan,nick):
  if not chan in userstable:
    log_error("UpdateLastActiveTime: %s spoke in %s, but %s not found in users table" % (nick, chan, chan))
    userstable[chan] = dict()
  if not nick in userstable[chan]:
    log_error("UpdateLastActiveTime: %s spoke in %s, but was not found in that channel's users table" % (nick, chan))
    userstable[chan][nick] = None
  userstable[chan][nick] = time.time()

def GetTimeSinceActive(chan,nick):
  if not chan in userstable:
    log_error("GetTimeSinceActive: channel %s not found in users table" % chan)
    return None
  if not nick in userstable[chan]:
    log_error("GetTimeSinceActive: %s not found in channel %s's users table" % (nick, chan))
    return None
  t = userstable[chan][nick]
  if t == None:
    return None
  dt = time.time() - t
  if dt < 0:
    log_error("GetTimeSinceActive: %s active in %s in the future" % (nick, chan))
    return None
  return dt

def GetActiveNicks(chan,seconds):
  nicks = []
  if not chan in userstable:
    return []
  now = time.time()
  for nick in userstable[chan]:
    t = userstable[chan][nick]
    if t == None:
      continue
    dt = now - t
    if dt < 0:
      log_error("GetActiveNicks: %s active in %s in the future" % (nick, chan))
      continue
    if dt < seconds:
      nicks.append(nick)
  return nicks

def GetUsersTable():
  return userstable

#def Op(to_op, chan):
#    SendIRC( 'MODE ' + chan + ' +o: ' + to_op)
#
#def DeOp(to_deop, chan):
#    SendIRC( 'MODE ' + chan + ' -o: ' + to_deop)
#
#def Voice(to_v, chan):
#    SendIRC( 'MODE ' + chan + ' +v: ' + to_v)
#
#def DeVoice(to_dv, chan):
#    SendIRC( 'MODE ' + chan + ' -v: ' + to_dv)

buffered_data = ""
def GetIRCLine():
  global buffered_data
  idx = buffered_data.find("\n")
  if idx == -1:
    try:
      (r,w,x)=select.select([irc.fileno()],[],[],1)
      if irc.fileno() in r:
        newdata=irc_recv(4096,socket.MSG_DONTWAIT)
      else:
        newdata = None
      if irc.fileno() in x:
        log_error('getline: IRC socket in exception set')
        newdata = None
    except Exception,e:
      log_error('getline: Exception: %s' % str(e))
      # Broken pipe when we get kicked for spam
      if str(e).find("Broken pipe") != -1:
        raise
      newdata = None
    if newdata == None:
      return None
    buffered_data+=newdata
  idx = buffered_data.find("\n")
  if idx == -1:
    ret = buffered_data
    buffered_data = ""
    return ret
  ret = buffered_data[0:idx+1]
  buffered_data = buffered_data[idx+1:]
  return ret

def IRCLoop(on_idle,on_identified,on_command):
  global userstable
  global registered_users
  global last_ping_time

  while True:
    action = None
    try:
      data = GetIRCLine()
    except Exception,e:
      log_warn('Exception from GetIRCLine, we were probably disconnected, reconnecting in 5 seconds')
      time.sleep(5)
      last_ping_time = time.time()
      reconnect_to_irc()
      continue

    # All that must be done even when nothing from IRC - data may be None here
    on_idle()

    if data == None:
      if time.time() - last_ping_time > config.irc_timeout_seconds:
        log_warn('%s seconds without PING, reconnecting in 5 seconds' % config.irc_timeout_seconds)
        time.sleep(5)
        last_ping_time = time.time()
        reconnect_to_irc()
      continue

    data = data.strip("\r\n")
    log_IRCRECV(data)

    # consider any IRC data as a ping
    last_ping_time = time.time()

    if data.find ( config.irc_welcome_line ) != -1:
      userstable = dict()
      registered_users.clear()
      SendTo("nickserv", "IDENTIFY %s" % irc_password)
      Join(config.irc_homechan)
      #ScanWho(None,[config.irc_homechan])

    if data.find ( 'PING' ) == 0:
      log_log('Got PING, replying PONG')
      last_ping_time = time.time()
      SendIRC ( 'PONG ' + data.split() [ 1 ])
      continue

    if data.find('ERROR :Closing Link:') == 0:
      log_warn('We were kicked from IRC, reconnecting in 5 seconds')
      time.sleep(5)
      last_ping_time = time.time()
      reconnect_to_irc()
      continue

    #--------------------------- Action check --------------------------------#
    if data.find(':') == -1:
      continue

    try:
        cparts = data.split(':')
        if len(cparts) < 2:
            continue
        if len(cparts) >= 3:
          text = cparts[2]
        else:
          text = ""
        parts = cparts[1].split(' ')
        who = parts[0]
        action = parts[1]
        chan = parts[2]
    except Exception, e:
        log_error('main parser: Exception, continuing: %s' % str(e))
        continue

    if action == None:
        continue

    #print 'text: ', text
    #print 'who: ', who
    #print 'action: ', action
    #print 'chan: ', chan

#    if data.find('#') != -1:
#        action = data.split('#')[0]
#        action = action.split(' ')[1]

#    if data.find('NICK') != -1:
#        if data.find('#') == -1:
#            action = 'NICK'

    #----------------------------- Actions -----------------------------------#
    try:
      if action == 'NOTICE':
        if text.find ('throttled due to flooding') >= 0:
          log_warn('Flood protection kicked in, outgoing messages lost')
        if who == "NickServ!NickServ@services.":
            #if text.find('Information on ') != -1:
            #    ns_nick = text.split(' ')[2].strip("\002")
            #    print 'NickServ says %s is registered' % ns_nick
            #    PerformNextAction(ns_nick, True)
            #elif text.find(' is not registered') != -1:
            #    ns_nick = text.split(' ')[0].strip("\002")
            #    print 'NickServ says %s is not registered' % ns_nick
            #    PerformNextAction(ns_nick, False)
            if text.find(' ACC ') != -1:
              stext  = text.split(' ')
              ns_nick = stext[0]
              ns_acc = stext[1]
              ns_status = stext[2]
              if ns_acc == "ACC":
                if ns_status == "3":
                  log_info('NickServ says %s is identified' % ns_nick)
                  on_identified(ns_nick, True)
                else:
                  log_info('NickServ says %s is not identified' % ns_nick)
                  on_identified(ns_nick, False)
              else:
                log_error('ACC line not as expected...')

      elif action == '352':
        try:
          who_chan = parts[3]
          who_chan_user = parts[7]
          if not who_chan_user in userstable[who_chan]:
            userstable[who_chan][who_chan_user] = None
          log_log("New list of users in %s: %s" % (who_chan, str(userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "who" line: %s: %s' % (data, str(e)))

      elif action == '353':
        try:
          who_chan = parts[4]
          who_chan_users = cparts[2].split(" ")
          for who_chan_user in who_chan_users:
            if not who_chan_user in userstable[who_chan]:
              if who_chan_user[0] == "@":
                who_chan_user = who_chan_user[1:]
              userstable[who_chan][who_chan_user] = None
          log_log("New list of users in %s: %s" % (who_chan, str(userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "who" line: %s: %s' % (data, str(e)))

      elif action == 'PRIVMSG':
        UpdateLastActiveTime(chan,GetNick(who))
        exidx = text.find('!')
        if exidx != -1 and len(text)>exidx+1 and text[exidx+1] in string.ascii_letters:
            cmd = text.split('!')[1]
            cmd = cmd.split(' ')
            cmd[0] = cmd[0].strip(' \t\n\r')

            log_log('Found command from %s: "%s" in channel "%s"' % (who, str(cmd), str(chan)))

            #if cmd[0] == 'join':
            #    Join('#' + cmd[1])
            #elif cmd[0] == 'part':
            #    Part('#' + cmd[1])
            on_command(cmd,chan,who)

      elif action == 'JOIN':
        nick = GetNick(who)
        log_info('%s joined the channel' % nick)
        if not chan in userstable:
          userstable[chan] = dict()
        if nick in userstable[chan]:
          log_warn('%s joined, but already in %s' % (nick, chan))
        else:
          userstable[chan][nick] = None
        log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'PART':
        nick = GetNick(who)
        log_info('%s left the channel' % nick)
        if not nick in userstable[chan]:
          log_warn('%s left, but was not in %s' % (nick, chan))
        else:
          del userstable[chan][nick]
        log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'QUIT':
        nick = GetNick(who)
        log_info('%s quit' % nick)
        removed_list = ""
        for chan in userstable:
          log_log("Checking in %s" % chan)
          if nick in userstable[chan]:
            removed_list = removed_list + " " + chan
            del userstable[chan][nick]
            log_log("New list of users in %s: %s" % (chan, str(userstable[chan].keys())))

      elif action == 'NICK':
        nick = GetNick(who)
        new_nick = text
        log_info('%s renamed to %s' % (nick, new_nick))
        for c in userstable:
          log_log('checking %s' % c)
          if nick in userstable[c]:
            del userstable[c][nick]
            if new_nick in userstable[c]:
              log_warn('%s is the new name of %s, but was already in %s' % (new_nick, nick, c))
            else:
              userstable[c][new_nick] = None
          log_log("New list of users in %s: %s" % (c, str(userstable[c].keys())))

    except Exception,e:
      log_error('Exception in top level action processing: %s' % str(e))

