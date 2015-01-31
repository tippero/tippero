#!/bin/python
#
# Cryptonote tipbot - utility functions
# Copyright 2014,2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import redis
import hashlib
import json
import httplib
import time
import tipbot.config as config
import tipbot.coinspecs as coinspecs
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.redisdb import *

registered_networks=dict()
networks=[]
cached_tipbot_balance=None
cached_tipbot_unlocked_balance=None
cached_tipbot_balance_timestamp=None

def GetPassword(name):
  try:
    f = open('tipbot-password.txt', 'r')
    for p in f:
      p = p.strip("\r\n")
      parts=p.split(':')
      if parts[0]==name:
        return parts[1]
  except Exception,e:
    log_error('could not fetch password: %s' % str(e))
    raise
    return "xxx"
  finally:
    f.close()

def IsParamPresent(parms,idx):
  return len(parms) > idx

def GetParam(parms,idx):
  if IsParamPresent(parms,idx):
    return parms[idx]
  return None

def GetPaymentID(link):
  salt="2u3g55bkwrui32fi3g4bGR$j5g4ugnujb-"+coinspecs.name+"-";
  p = hashlib.sha256(salt+link.identity()).hexdigest();
  try:
    redis_hset("paymentid",p,link.identity())
  except Exception,e:
    log_error('GetPaymentID: failed to set payment ID for %s to redis: %s' % (link.identity(),str(e)))
  return p

def GetIdentityFromPaymentID(p):
  if not redis_hexists("paymentid",p):
    log_log('PaymentID %s not found' % p)
    return None
  identity = redis_hget("paymentid",p)
  log_log('PaymentID %s => %s' % (p, str(identity)))
  # HACK - grandfathering pre-network payment IDs
  if identity.index(':') == -1:
    log_warn('Pre-network payment ID found, assuming freenode')
    identity = "freenode:"+identity
  return identity

def IsValidAddress(address):
  if len(address) < coinspecs.address_length[0] or len(address) > coinspecs.address_length[1]:
    return False
  for prefix in coinspecs.address_prefix:
    if address.startswith(prefix):
      return True
  return False

def AmountToString(amount):
  if amount == None:
    amount = 0
  lamount=long(amount)
  samount = None
  if lamount == 0:
    samount = "0 %s" % coinspecs.name
  else:
    for den in coinspecs.denominations:
      if lamount < den[0]:
        samount = "%.16g %s" % (float(lamount) / den[1], den[2])
        break
  if not samount:
      samount = "%.16g %s" % (float(lamount) / coinspecs.atomic_units, coinspecs.name)
  return samount

def TimeToString(seconds):
  seconds=float(seconds)
  if seconds < 1e-3:
    return "%.2f microseconds" % (seconds*1e6)
  if seconds < 1:
    return "%.2f milliseconds" % (seconds*1e3)
  if seconds < 60:
    return "%.2f seconds" % (seconds)
  if seconds < 3600:
    return "%.2f minutes" % (seconds / 60)
  if seconds < 3600 * 24:
    return "%.2f hours" % (seconds / 3600)
  if seconds < 3600 * 24 * 30.5:
    return "%.2f days" % (seconds / (3600*24))
  if seconds < 3600 * 24 * 365.25:
    return "%.2f months" % (seconds / (3600*24*30.5))
  if seconds < 3600 * 24 * 365.25 * 100:
    return "%.2f years" % (seconds / (3600*24*365.25))
  if seconds < 3600 * 24 * 365.25 * 1000:
    return "%.2f centuries" % (seconds / (3600*24*365.25 * 100))
  if seconds < 3600 * 24 * 365.25 * 1000000:
    return "%.2f millenia" % (seconds / (3600*24*365.25 * 100))
  return "like, forever, dude"

def SendJSONRPCCommand(host,port,method,params):
  try:
    http = httplib.HTTPConnection(host,port,timeout=20)
  except Exception,e:
    log_error('SendJSONRPCCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  d = dict(id="0",jsonrpc="2.0",method=method,params=params)
  try:
    j = json.dumps(d).encode()
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to encode JSON: %s' % str(e))
    http.close()
    raise
  log_log('SendJSONRPCCommand: Sending json as body: %s' % j)
  headers = None
  try:
    http.request("POST","/json_rpc",body=j)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  if response.status != 200:
    log_error('SendJSONRPCCommand: Error, received reply status %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendJSONRPCCommand: Received reply status %s: %s' % (response.status, str(s).replace('\r\n',' ').replace('\n',' ')))
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendJSONRPCCommand: Failed to decode JSON: %s' % str(e))
    http.close()
    raise
  http.close()
  return j

def SendHTMLCommand(host,port,method):
  try:
    http = httplib.HTTPConnection(host,port,timeout=20)
  except Exception,e:
    log_error('SendHTMLCommand: Error connecting to %s:%u: %s' % (host, port, str(e)))
    raise
  headers = None
  try:
    http.request("POST","/"+method)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to post request: %s' % str(e))
    http.close()
    raise
  response = http.getresponse()
  if response.status != 200:
    log_error('SendHTMLCommand: Error, received reply status %s' % str(response.status))
    http.close()
    raise RuntimeError("Error "+response.status)
  s = response.read()
  log_log('SendHTMLCommand: Received reply status %s: %s' % (response.status,s.replace('\r\n',' ').replace('\n',' ')))
  try:
    j = json.loads(s)
  except Exception,e:
    log_error('SendHTMLCommand: Failed to decode JSON: %s' % str(e))
    http.close()
    raise
  http.close()
  return j

def SendWalletJSONRPCCommand(method,params):
  return SendJSONRPCCommand(config.wallet_host,config.wallet_port,method,params)

def SendDaemonJSONRPCCommand(method,params):
  return SendJSONRPCCommand(config.daemon_host,config.daemon_port,method,params)

def SendDaemonHTMLCommand(method):
  return SendHTMLCommand(config.daemon_host,config.daemon_port,method)

def RetrieveTipbotBalance(force_refresh=False):
  global cached_tipbot_balance, cached_tipbot_unlocked_balance, cached_tipbot_balance_timestamp
  if not force_refresh and cached_tipbot_balance_timestamp and time.time()-cached_tipbot_balance_timestamp < config.tipbot_balance_cache_time:
    return cached_tipbot_balance, cached_tipbot_unlocked_balance

  j = SendWalletJSONRPCCommand("getbalance",None)
  if not "result" in j:
    log_error('RetrieveTipbotBalance: result not found in reply')
    raise RuntimeError("")
    return
  result = j["result"]
  if not "balance" in result:
    log_error('RetrieveTipbotBalance: balance not found in result')
    raise RuntimeError("")
    return
  if not "unlocked_balance" in result:
    log_error('RetrieveTipbotBalance: unlocked_balance not found in result')
    raise RuntimeError("")
    return
  balance = result["balance"]
  unlocked_balance = result["unlocked_balance"]
  log_log('RetrieveTipbotBalance: balance: %s' % str(balance))
  log_log('RetrieveTipbotBalance: unlocked_balance: %s' % str(unlocked_balance))
  pending = long(balance)-long(unlocked_balance)
  if pending < 0:
    log_error('RetrieveTipbotBalance: Negative pending balance! balance %s, unlocked %s' % (str(balance),str(unlocked_balance)))
    raise RuntimeError("")
    return
  cached_tipbot_balance_timestamp=time.time()
  cached_tipbot_balance=balance
  cached_tipbot_unlocked_balance=unlocked_balance
  return balance, unlocked_balance

def RetrieveBalance(link):
  try:
    balance = redis_hget("balances",link.identity()) or 0
    confirming = redis_hget("confirming_payments",link.identity()) or 0
    return long(balance), long(confirming)
  except Exception, e:
    log_error('RetrieveBalance: exception: %s' % str(e))
    raise

def IdentityFromString(link,s):
  if s.find(':') == -1:
    network = link.network
    nick=s
  else:
    parts=s.split(':')
    network_name=parts[0]
    network=GetNetworkByName(network_name)
    nick=parts[1]
  return network.name+':'+network.canonicalize(nick)

def NickFromIdentity(identity):
  return identity.split(':')[1]

def RegisterNetwork(name,type):
  registered_networks[name]=type

def AddNetwork(network):
  networks.append(network)

def GetNetworkByName(name):
  for network in networks:
    if network.name==name:
      return network
  return None

def GetNetworkByType(type):
  for network in networks:
    if isinstance(network,type):
      return network
  return None

