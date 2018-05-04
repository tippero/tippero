#!/bin/python
#
# Cryptonote tipbot - IRC commands
# Copyright 2015 moneromooo
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
import base64
import re
import tipbot.config as config
from tipbot.log import log, log_error, log_warn, log_info, log_log
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.network import *
from tipbot.command_manager import *

irc_min_send_delay = 0.05 # seconds
irc_max_send_delay = 1.2 # seconds

def GetNick(data):                            # Return Nickname
  nick = data.split('!')[0]
  nick = nick.replace(':', ' ')
  nick = nick.replace(' ', '')
  nick = nick.strip(' \t\n\r')
  return nick.lower()

class IRCNetwork(Network):
  def __init__(self,name):
    Network.__init__(self,name)
    self.userstable = dict()
    self.registered_users = set()
    self.last_send_time=0
    self.last_ping_time=0
    self.current_send_delay = irc_min_send_delay
    self.quitting = False
    self.buffered_data = ""
    self.known = {}

  def connect(self):
    try:
      cfg=config.network_config[self.name]
      host=cfg['host']
      port=cfg['port']
      login=cfg['login']
      password=GetPassword(self.name)
      delay=cfg['delay']
      self.use_ssl=cfg['ssl']
      self.use_sasl=cfg['sasl']
      self.welcome_line=cfg['welcome_line']
      self.timeout_seconds=cfg['timeout_seconds']
      self.channels=cfg['channels']
      if self.use_sasl:
        self.sasl_name=cfg['sasl_name']
    except Exception,e:
      log_error('Configuration not found for %s: %s' % (self.name, str(e)))
      return False
    return self._connect(host,port,login,password,delay)

  def disconnect(self):
    self._irc_sendmsg ('QUIT')
    if self.sslirc:
      self.sslirc.close()
      self.sslirc = None
    self.irc.close()
    self.irc = None

  def send_to(self,where,msg):
    for line in msg.split("\n"):
      line=line.strip('\r')
      if len(line)>0:
        self._irc_sendmsg('PRIVMSG '+where+' :'+line)

  def send_group(self,group,msg,data=None):
    self.send_to(group.name,msg)

  def send_user(self,user,msg,data=None):
    self.send_to(user.nick,msg)

  def is_identified(self,link):
    return link.identity() in self.registered_users

  def canonicalize(self,nick):
    return nick.lower()

  def join(self,chan):
    self._irc_sendmsg('JOIN '+chan)

  def part(self,chan):
    self._irc_sendmsg('PART '+chan)

  def quit(self,msg=None):
    self.quitting = True
    if msg:
      self._irc_sendmsg('QUIT%s '%msg)
    else:
      self._irc_sendmsg('QUIT')

  def dump_users(self):
    log_info('users on %s: %s' % (self.name,str(self.userstable)))

  def update_users_list(self,chan):
    if chan:
      self._irc_sendmsg('WHO '+chan)

  def update_last_active_time(self,chan,nick):
    if chan[0] != '#':
      return
    if not chan in self.userstable:
      log_error("IRCNetwork:update_last_active_time: %s spoke in %s, but %s not found in users table" % (nick, chan, chan))
      self.userstable[chan] = dict()
    if not nick in self.userstable[chan]:
      log_error("IRCNetwork:update_last_active_time: %s spoke in %s, but was not found in that channel's users table" % (nick, chan))
      self.userstable[chan][nick] = None
    self.userstable[chan][nick] = time.time()

  def get_last_active_time(self,nick,chan):
    if not chan in self.userstable:
      log_error("IRCNetwork:get_last_active_time: channel %s not found in users table" % chan)
      return None
    if not nick in self.userstable[chan]:
      log_error("IRCNetwork:get_last_active_time: %s not found in channel %s's users table" % (nick, chan))
      return None
    return self.userstable[chan][nick]

  def get_active_users(self,seconds,chan):
    nicks = []
    if not chan in self.userstable:
      return []
    now = time.time()
    for nick in self.userstable[chan]:
      t = self.userstable[chan][nick]
      if t == None:
        continue
      dt = now - t
      if dt < 0:
        log_error("IRCNetwork:get_active_users: %s active in %s in the future" % (nick, chan))
        continue
      if dt < seconds:
        nicks.append(Link(self,User(self,nick),Group(self,chan)))
    return nicks

  def get_users(self,chan):
    nicks = []
    if not chan in self.userstable:
      return []
    for nick in self.userstable[chan]:
      nicks.append(Link(self,User(self,nick),Group(self,chan)))
    return nicks

  def is_acceptable_command_prefix(self,s):
    s=s.strip()
    log_log('checking whether %s is an acceptable command prefix' % s)
    if s=="":
      return True
    if re.match("%s[\t ]*[:,]?$"%config.tipbot_name, s):
      return True
    return False

  def evict_known(self, nick):
    del self.known[nick]
    self.registered_users.discard(Link(self,User(self,nick),None).identity())
    log_info("now unknown: " + Link(self,User(self,nick),None).identity())

  def add_known(self, nick):
    self.known[nick] = time.time()
    self.registered_users.discard(Link(self,User(self,nick),None).identity())
    log_info("now known: " + Link(self,User(self,nick),None).identity())

  def is_known(self, nick):
    return time.time() - self.known[nick] if nick in self.known else 0

  def update(self):
    try:
      data=self._getline()
    except Exception,e:
      log_warn('Exception from IRCNetwork:_getline, we were probably disconnected, reconnecting in %s seconds' % self.timeout_seconds)
      time.sleep(5)
      self.last_ping_time = time.time()
      self._reconnect()
      return True
    if data == None:
      if time.time() - self.last_ping_time > self.timeout_seconds:
        log_warn('%s seconds without PING, reconnecting in 5 seconds' % self.timeout_seconds)
        time.sleep(5)
        self.last_ping_time = time.time()
        self._reconnect()
      return True

    data = data.strip("\r\n")
    self._log_IRCRECV(data)

    # consider any IRC data as a ping
    self.last_ping_time = time.time()

    if data.find ( self.welcome_line ) != -1:
      self.userstable = dict()
      self.registered_users.clear()
      if not self.use_sasl:
        self.login()
      for chan in self.channels:
        self.join(chan)
        #ScanWho(None,[chan])

    if data.find ( 'PING' ) == 0:
      self.last_ping_time = time.time()
      self._irc_sendmsg ( 'PONG ' + data.split() [ 1 ])
      return True

    if data.startswith('AUTHENTICATE +'):
      if self.use_sasl:
        authstring = self.sasl_name + chr(0) + self.sasl_name + chr(0) + self.password
        self._irc_sendmsg('AUTHENTICATE %s' % base64.b64encode(authstring))
      else:
        log_warn('Got AUTHENTICATE while not using SASL')

    if data.find('ERROR :Closing Link:') == 0:
      if self.quitting:
        log_info('IRC stopped, bye')
        return False
      log_warn('We were kicked from IRC, reconnecting in 5 seconds')
      time.sleep(5)
      self.last_ping_time = time.time()
      self._reconnect()
      return True

    if data.find(':') == -1:
      return True

    try:
      cparts = data.lstrip(':').split(' :')
      if len(cparts) == 0:
        log_warn('No separator found, ignoring line')
        return True
      #if len(cparts) >= 9:
      #  idx_colon = data.find(':',1)
      #  idx_space = data.find(' ')
      #  if idx_space and idx_colon < idx_space and re.search("@([0-9a-fA-F]+:){7}[0-9a-fA-F]+", data):
      #    log_info('Found IPv6 address in non-text, restructuring')
      #    idx = data.rfind(':')
      #    cparts = [ cparts[0], "".join(cparts[1:]) ]
      if len(cparts) >= 2:
        text = cparts[1]
      else:
        text = ""
      parts = cparts[0].split(' ')
      who = parts[0]
      action = parts[1]
      if len(parts) >= 3:
        chan = parts[2]
      else:
        chan = None
    except Exception, e:
      log_error('main parser: Exception, ignoring line: %s' % str(e))
      return True

    if action == None:
      return True

    #print 'cparts: ', str(cparts)
    #print 'parts: ', str(parts)
    #print 'text: ', text
    #print 'who: ', who
    #print 'action: ', action
    #print 'chan: ', chan

    try:
      if action == 'CAP':
        if parts[2] == '*' and parts[3] == 'ACK':
          log_info('CAP ACK received from server')
          self._irc_sendmsg('AUTHENTICATE PLAIN')
        elif parts[2] == '*' and parts[3] == 'NAK':
          log_info('CAP NAK received from server')
          log_error('Failed to negotiate SASL')
          exit()
        else:
          log_warn('Unknown CAP line received from server: %s' % data)
      if action == 'NOTICE':
        if text.find ('throttled due to flooding') >= 0:
          log_warn('Flood protection kicked in, outgoing messages lost')
        ret = self.on_notice(who,text)
        if ret:
          return ret

      elif action == '903':
        log_info('SASL authentication success')
        self._irc_sendmsg('CAP END')
      elif action in ['902', '904', '905', '906']:
        log_error('SASL authentication failed (%s)' % action)

      elif action == '352':
        try:
          who_chan = parts[3]
          who_chan_user = parts[7].lower()
          if not who_chan_user in self.userstable[who_chan]:
            self.userstable[who_chan][who_chan_user] = None
          log_log("New list of users in %s: %s" % (who_chan, str(self.userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "352" line: %s: %s' % (data, str(e)))

      elif action == '353':
        try:
          who_chan = parts[4]
          who_chan_users = cparts[1].split(" ")
          log_info('who_chan: %s' % str(who_chan))
          log_info('who_chan_users: %s' % str(who_chan_users))
          for who_chan_user in who_chan_users:
            who_chan_user=who_chan_user.lower()
            if not who_chan_user in self.userstable[who_chan]:
              if who_chan_user[0] in ["@","+"]:
                who_chan_user = who_chan_user[1:]
              self.userstable[who_chan][who_chan_user] = None
            self.add_known(who_chan_user)
          log_log("New list of users in %s: %s" % (who_chan, str(self.userstable[who_chan].keys())))
        except Exception,e:
          log_error('Failed to parse "353" line: %s: %s' % (data, str(e)))

      elif action == 'PRIVMSG':
        self.update_last_active_time(chan,GetNick(who))
        # resplit to avoid splitting text that contains ':'
        text = data.split(' :',1)[1]
        if self.on_event:
          self.on_event('message',link=Link(self,User(self,GetNick(who),who),Group(self,chan)),message=text)
        exidx = text.find('!')
        if exidx != -1 and len(text)>exidx+1 and text[exidx+1] in string.ascii_letters and self.is_acceptable_command_prefix(text[:exidx]):
            cmd = text.split('!')[1]
            cmd = cmd.split(' ')
            while '' in cmd:
              cmd.remove('')
            cmd[0] = cmd[0].strip(' \t\n\r')

            log_log('Found command from %s: "%s" in channel "%s"' % (who, str(cmd), str(chan)))
            if self.on_command:
              self.on_command(Link(self,User(self,GetNick(who)),Group(self,chan) if chan[0]=='#' else None),cmd)
            return True

      elif action == 'JOIN':
        nick = GetNick(who)
        self.add_known(nick)
        log_info('%s joined the channel' % nick)
        if not chan in self.userstable:
          self.userstable[chan] = dict()
        if nick in self.userstable[chan]:
          log_warn('%s joined, but already in %s' % (nick, chan))
        else:
          self.userstable[chan][nick] = None
        log_log("New list of users in %s: %s" % (chan, str(self.userstable[chan].keys())))
        if self.on_event:
          self.on_event('user-joined',link=Link(self,User(self,nick,who),Group(self,chan)))

      elif action == 'PART':
        nick = GetNick(who)
        self.evict_known(nick)
        log_info('%s left the channel' % nick)
        if not nick in self.userstable[chan]:
          log_warn('%s left, but was not in %s' % (nick, chan))
        else:
          del self.userstable[chan][nick]
        log_log("New list of users in %s: %s" % (chan, str(self.userstable[chan].keys())))
        if self.on_event:
          self.on_event('user-left',link=Link(self,User(self,nick),Group(self,chan)))

      elif action == 'QUIT':
        nick = GetNick(who)
        self.evict_known(nick)
        log_info('%s quit' % nick)
        removed_list = ""
        for chan in self.userstable:
          log_log("Checking in %s" % chan)
          if nick in self.userstable[chan]:
            removed_list = removed_list + " " + chan
            del self.userstable[chan][nick]
            log_log("New list of users in %s: %s" % (chan, str(self.userstable[chan].keys())))
        if self.on_event:
          self.on_event('user-left',link=Link(self,User(self,nick)))

      elif action == 'KICK':
        nick = parts[3].lower()
        log_info('%s was kicked' % nick)
        removed_list = ""
        for chan in self.userstable:
          log_log("Checking in %s" % chan)
          if nick in self.userstable[chan]:
            removed_list = removed_list + " " + chan
            del self.userstable[chan][nick]
            log_log("New list of users in %s: %s" % (chan, str(self.userstable[chan].keys())))
        if self.on_event:
          self.on_event('user-left',link=Link(self,User(self,nick)))

      elif action == 'NICK':
        nick = GetNick(who)
        new_nick = cparts[len(cparts)-1].lower()
        log_info('%s renamed to %s' % (nick, new_nick))
        self.evict_known(nick)
        self.add_known(new_nick)
        for c in self.userstable:
          log_log('checking %s' % c)
          if nick in self.userstable[c]:
            del self.userstable[c][nick]
            if new_nick in self.userstable[c]:
              log_warn('%s is the new name of %s, but was already in %s' % (new_nick, nick, c))
            else:
              self.userstable[c][new_nick] = None
          log_log("New list of users in %s: %s" % (c, str(self.userstable[c].keys())))
        if self.on_event:
          self.on_event('user-name',link=Link(self,User(self,new_nick),Group(self,chan)),old_name=nick)

    except Exception,e:
      log_error('Exception in top level action processing: %s' % str(e))

    return True

  def _log_IRCRECV(self,msg):
    log("IRCRECV",msg)

  def _log_IRCSEND(self,msg):
    log("IRCSEND",msg)

  def _irc_recv(self,size,flags=None):
    if self.use_ssl:
      return self.sslirc.read(size)
    else:
      return self.irc.recv(size,flags)

  def _irc_send(self,data):
    if self.use_ssl:
      return self.sslirc.write(data)
    else:
      return self.irc.send(data)

  def _irc_sendmsg(self,msg):
    t = time.time()
    dt = t - self.last_send_time
    if dt < self.current_send_delay:
      time.sleep (self.current_send_delay - dt)
      self.current_send_delay = self.current_send_delay * 1.5
      if self.current_send_delay > irc_max_send_delay:
        self.current_send_delay = irc_max_send_delay
    else:
      while dt > self.current_send_delay * 1.5:
        dt = dt - self.current_send_delay
        self.current_send_delay = self.current_send_delay / 1.5
        if self.current_send_delay < irc_min_send_delay:
          self.current_send_delay = irc_min_send_delay
          break

    self._log_IRCSEND(msg)
    self._irc_send(msg + '\r\n')
    self.last_send_time = time.time()

  def _getline(self):
    idx = self.buffered_data.find("\n")
    if idx == -1:
      try:
        (r,w,x)=select.select([self.irc.fileno()],[],[],1)
        if self.irc.fileno() in r:
          newdata=self._irc_recv(4096,socket.MSG_DONTWAIT)
          if len(newdata) == 0:
            raise RuntimeError('0 bytes received, EOF')
        else:
          newdata = None
        if self.irc.fileno() in x:
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
      self.buffered_data+=newdata
    idx = self.buffered_data.find("\n")
    if idx == -1:
      ret = self.buffered_data
      self.buffered_data = ""
      return ret
    ret = self.buffered_data[0:idx+1]
    self.buffered_data = self.buffered_data[idx+1:]
    return ret

  def _connect(self,host,port,login,password,delay):
    self.host=host
    self.port=port
    self.login=login
    self.password=password
    self.line_delay=delay

    log_info('Connecting to IRC at %s:%u' % (host, port))
    self.last_send_time=0
    self.last_ping_time = time.time()
    self.quitting = False
    self.buffered_data = ""
    self.userstable=dict()
    self.registered_users=set()
    try:
      self.irc = socket.socket ( socket.AF_INET, socket.SOCK_STREAM )
      if self.use_ssl:
        try:
          raise RuntimeError('')
          self.irc_ssl_context = ssl.create_default_context()
          self.sslirc = self.irc_ssl_context.wrap_socket(self.irc, host)
          self.sslirc.connect ( ( host, port ) )
        except Exception,e:
          log_warn('Failed to create SSL context, using fallback code: %s' % str(e))
          self.irc.connect ( ( host, port ) )
          self.sslirc = socket.ssl(self.irc)
    except Exception, e:
      log_error( 'Error initializing IRC: %s' % str(e))
      return False
    self._log_IRCRECV(self._irc_recv(4096))
    if self.use_sasl:
      self._irc_sendmsg('CAP REQ :sasl')
    else:
      self._irc_sendmsg ( 'PASS *********')
    self._irc_sendmsg ( 'NICK %s' % login)
    self._irc_sendmsg ( 'USER %s %s %s :%s' % (login, login, login, login))
    return True

  def _reconnect(self):
    return self._connect(self.host,self.port,self.login,self.password,self.line_delay)



def JoinChannel(link,cmd):
  jchan = GetParam(cmd,1)
  if not jchan:
    link.send('Usage: join <channel>')
    return
  if jchan[0] != '#':
    link.send('Channel name must start with #')
    return
  network=GetNetworkByType(IRCNetwork)
  if not network:
    link.send('No IRC network found')
    return
  network.join(jchan)

def PartChannel(link,cmd):
  pchan = GetParam(cmd,1)
  if pchan:
    if pchan[0] != '#':
      link.send('Channel name must start with #')
      return
  else:
    pchan = chan
  network=GetNetworkByType(IRCNetwork)
  if not network:
    link.send('No IRC network found')
    return
  network.part(pchan)

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
RegisterNetwork("irc",IRCNetwork)
