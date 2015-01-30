#!/bin/python
#
# Cryptonote tipbot - network
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

from link import Link
from user import User
from group import Group

class Network:
  def __init__(self,name):
    self.name=name

  def connect(self):
    pass

  def disconnect(self):
    pass

  def send_group(self,group,msg,data=None):
    pass

  def send_user(self,user,msg,data=None):
    pass

  def identify(self,link):
    pass

  def dump_users(self):
    pass

  def set_callbacks(self,on_command,on_identified):
    self.on_command=on_command
    self.on_identified=on_identified

  def get_last_active_time(user_name,group_name=None):
    return None

  def get_active_users(seconds,group_name=None):
    return []

  def get_users(group_name=None):
    return []

  def update_users_list(self,group_name=None):
    pass

  def canonicalize(self,name):
    return name

  def update(self):
    return True

  def quit(self,msg=None):
    pass
