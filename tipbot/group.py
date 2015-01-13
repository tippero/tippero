#!/bin/python
#
# Cryptonote tipbot - group
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

class Group:
  def __init__(self,network,name):
    self.network=network
    self.name=name

  def send(self,msg):
    self.network.send_group(self,msg)

