#!/bin/python
#
# Cryptonote tipbot - Freenode
# Copyright 2015 moneromooo
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
from tipbot.command_manager import *
from irc import *

class FreenodeNetwork(IRCNetwork):
  def __init__(self):
    IRCNetwork.__init__(self,"freenode")

  def login(self):
    self.send_to("nickserv", "IDENTIFY %s" % self.password)

  def identify(self,link):
    nick = link.user.nick
    log_info('Asking nickserv whether %s is identified' % nick)
    self.send_to('nickserv', "ACC " + nick)

  def on_notice(self,who,text):
    if who == "NickServ!NickServ@services.":
      if text.find(' ACC ') != -1:
        stext  = text.split(' ')
        ns_nick = stext[0]
        ns_acc = stext[1]
        ns_status = stext[2]
        if ns_acc == "ACC":
          ns_link=Link(self,User(self,ns_nick),None)
          if ns_status == "3":
            log_info('NickServ says %s is identified' % ns_nick)
            self.registered_users.add(ns_link.identity())
            if self.on_identified:
              self.on_identified(ns_link,True)
          else:
            log_info('NickServ says %s is not identified' % ns_nick)
            self.registered_users.discard(ns_link.identity())
            if self.on_identified:
              self.on_identified(ns_link,False)
        else:
          log_error('ACC line not as expected...')
    return True

