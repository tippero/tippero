#!/bin/python
#
# Cryptonote tipbot - logging
# Copyright 2014 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import time

def log(stype,msg):
  header = "%s\t%s\t" % (time.ctime(time.time()),stype)
  print "%s%s" % (header, str(msg).replace("\n","\n"+header))

def log_error(msg):
  log("ERROR",msg)

def log_warn(msg):
  log("WARNING",msg)

def log_info(msg):
  log("INFO",msg)

def log_log(msg):
  log("LOG",msg)

def log_IRCRECV(msg):
  log("IRCRECV",msg)

def log_IRCSEND(msg):
  log("IRCSEND",msg)

