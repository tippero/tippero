#!/bin/python
#
# Cryptonote tipbot - user
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

class User:
  def __init__(self,network,nick,ident=None):
    self.network=network
    self.nick=nick
    self.ident=ident

  def check_registered(self):
    pass

  def is_registered(self):
    if not self.registered:
      self.check_registered()
    return self.registered

