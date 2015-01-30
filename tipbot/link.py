#!/bin/python
#
# Cryptonote tipbot - link
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

from tipbot.log import log_error, log_warn, log_info, log_log

class Link:
  def __init__(self,network,user,group=None,data=None):
    self.network=network
    self.user=user
    self.group=group
    self.data=data
    self.identity_string = self.network.name+":"+network.canonicalize(self.user.nick)
    self.batch_message = None
    self.batch_message_private = None

  def __repr__(self):
    return '<link: network %s, user %s, group %s, data %s>' % (str(self.network),str(self.user),str(self.group),str(self.data))

  def identity(self):
    return self.identity_string

  def send(self,msg):
    if self.batch_message != None:
      self.batch_message.append(msg)
    else:
      return self._send(msg)

  def send_private(self,msg):
    if self.batch_message_private != None:
      self.batch_message_private.append(msg)
    else:
      return self._send_private(msg)

  def _send(self,msg):
    if self.group:
      self.network.send_group(self.group,msg,self.data)
    else:
      self.network.send_user(self.user,msg,self.data)

  def _send_private(self,msg):
    self.network.send_user(self.user,msg,self.data)

  def batch_send_start(self):
    self.batch_message = []
    self.batch_message_private = []

  def batch_send_done(self):
    if self.batch_message != None:
      if len(self.batch_message)>0:
        self._send("\n".join(self.batch_message))
      self.batch_message = None
    if self.batch_message_private != None:
      if len(self.batch_message_private)>0:
        self._send_private("\n".join(self.batch_message_private))
      self.batch_message_private = None
