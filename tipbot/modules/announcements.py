#!/bin/python
#
# Cryptonote tipbot - Announcement
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import string
import time
import threading
import re
import praw
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.network import *

def Announce(link,cmd):
  if not GetParam(cmd,1):
    link.send('usage: !announce <text>')
    return
  nextid=redis_get('cryptokingdom:announcements:nextid')
  if nextid==None:
    nextid=1
  nextid=long(nextid)
  text = " ".join(cmd[1:])
  redis_hset('cryptokingdom:announcements',nextid,'From %s: %s'%(link.user.nick,text))
  nextid+=1
  redis_set('cryptokingdom:announcements:nextid',nextid)

def Announcements(link,cmd):
  announcements=redis_hgetall('cryptokingdom:announcements')
  if announcements==None or len(announcements)==0:
    link.send('There are no announcements at this time')
    return
  for a in announcements:
    link.send('%s: %s' % (str(a),str(announcements[a])))

def Cancel(link,cmd):
  which=GetParam(cmd,1)
  if which == None:
    link.send(link,'usage: !cancel <number>')
    return
  if not redis_hexists('cryptokingdom:announcements',which):
    link.send(link,'Announcement not found: %s' % str(which))
    return
  redis_hdel('cryptokingdom:announcements',which)

def Help(link):
  link.send_private('Announce anything that you want others to know')
  link.send_private('Offers, auctions, other information')



RegisterModule({
  'name': __name__,
  'help': Help,
})
RegisterCommand({
  'module': __name__,
  'name': 'announce',
  'parms': '<text>',
  'function': Announce,
  'registered': True,
  'help': "Announce anything that may interest others"
})
RegisterCommand({
  'module': __name__,
  'name': 'announcements',
  'function': Announcements,
  'registered': True,
  'help': "Show current announcements"
})
RegisterCommand({
  'module': __name__,
  'name': 'cancel',
  'parms': '<number>',
  'function': Cancel,
  'registered': True,
  'help': "Cancel a given annoucement by its number"
})
