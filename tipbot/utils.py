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
import threading
import math
import string
import random
from Crypto.Random.random import getrandbits
from decimal import *
import tipbot.config as config
import tipbot.coinspecs as coinspecs
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.link import Link
from tipbot.redisdb import *

registered_networks=dict()
networks=[]
cached_tipbot_balance=None
cached_tipbot_unlocked_balance=None
cached_tipbot_balance_timestamp=None

core_lock = threading.RLock()

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

def GetPaymentID(link,random=False):
  salt="2u3g55bkwrui32fi3g4bGR$j5g4ugnujb-"+coinspecs.name+"-";
  if random:
    salt = salt + "-" + str(time.time()) + "-" + str(getrandbits(128))
  p = hashlib.sha256(salt+link.identity()).hexdigest();
  try:
    redis_hset("paymentid",p,link.identity())
  except Exception,e:
    log_error('GetPaymentID: failed to set payment ID for %s to redis: %s' % (link.identity(),str(e)))
  return p

def GetRandomPaymentID(link):
  return GetPaymentID(link, True)

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

def IsAddressLengthValid(address):
  if type(coinspecs.address_length[0]) == list:
    for allist in coinspecs.address_length:
      if len(address) >= allist[0] and len(address) <= allist[1]:
        return True
  else:
    if len(address) >= coinspecs.address_length[0] and len(address) <= coinspecs.address_length[1]:
      return True
  return False

def IsValidAddress(address):
  if not IsAddressLengthValid(address):
    return False
  for prefix in coinspecs.address_prefix:
    if address.startswith(prefix):
      return True
  return False

def IsValidPaymentID(payment_id):
  if len(payment_id)!=64:
    return False
  for char in payment_id:
    if char not in string.hexdigits:
      return False
  return True

# Code taken from the Python documentation
def moneyfmt(value, places=2, curr='', sep=',', dp='.',
             pos='', neg='-', trailneg=''):
    """Convert Decimal to a money formatted string.

    places:  required number of places after the decimal point
    curr:    optional currency symbol before the sign (may be blank)
    sep:     optional grouping separator (comma, period, space, or blank)
    dp:      decimal point indicator (comma or period)
             only specify as blank when places is zero
    pos:     optional sign for positive numbers: '+', space or blank
    neg:     optional sign for negative numbers: '-', '(', space or blank
    trailneg:optional trailing minus indicator:  '-', ')', space or blank

    >>> d = Decimal('-1234567.8901')
    >>> moneyfmt(d, curr='$')
    '-$1,234,567.89'
    >>> moneyfmt(d, places=0, sep='.', dp='', neg='', trailneg='-')
    '1.234.568-'
    >>> moneyfmt(d, curr='$', neg='(', trailneg=')')
    '($1,234,567.89)'
    >>> moneyfmt(Decimal(123456789), sep=' ')
    '123 456 789.00'
    >>> moneyfmt(Decimal('-0.02'), neg='<', trailneg='>')
    '<0.02>'

    """
    q = Decimal(10) ** -places      # 2 places --> '0.01'
    sign, digits, exp = value.quantize(q).as_tuple()
    result = []
    digits = map(str, digits)
    build, next = result.append, digits.pop
    if sign:
        build(trailneg)
    for i in range(places):
        build(next() if digits else '0')
    build(dp)
    if not digits:
        build('0')
    i = 0
    while digits:
        build(next())
        i += 1
        if i == 3 and digits:
            i = 0
            build(sep)
    build(curr)
    build(neg if sign else pos)
    s = ''.join(reversed(result))

    if dp in s:
      s=s.strip('0').rstrip(dp)
    if s=="" or s[0]==dp:
      s="0"+s
    return s

def AmountToString(amount):
  if amount == None:
    amount = 0
  lamount=long(amount)
  samount = None
  if lamount == 0:
    samount = "0 %s" % coinspecs.name
  else:
    places=long(0.5+math.log10(coinspecs.atomic_units))
    for den in coinspecs.denominations:
      if lamount < den[0]:
        samount = moneyfmt(Decimal(lamount)/Decimal(den[1]),places=places) + " " + den[2]
        break
  if not samount:
    samount = moneyfmt(Decimal(lamount)/Decimal(coinspecs.atomic_units),places=places) + " " + coinspecs.name
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

def StringToUnits(s):
  try:
    return long(Decimal(s)*long(coinspecs.atomic_units))
  except Exception,e:
    log_error('Failed to convert %s to units: %s' % (s,str(e)))
    raise

def SendJSONRPCCommand(host,port,method,params):
  try:
    http = httplib.HTTPConnection(host,port,timeout=config.rpc_timeout)
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
    http = httplib.HTTPConnection(host,port,timeout=config.rpc_timeout)
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

def GetAccount(link_or_identity):
  if isinstance(link_or_identity,Link):
    identity=link_or_identity.identity()
  else:
    identity=link_or_identity
  account = redis_hget('accounts',identity)
  if account == None:
    log_info('No account found for %s, creating new one' % identity)
    next_account_id = long(redis_get('next_account_id') or 0)
    account = next_account_id
    if redis_hexists('accounts',account):
      raise RuntimeError('Next account ID already exists (%d)', account)
    redis_hset('accounts',identity,account)
    next_account_id += 1
    redis_set('next_account_id',next_account_id)
  return account

def RetrieveBalance(link):
  try:
    account = GetAccount(link)
    balance = redis_hget("balances",account) or 0
    confirming = redis_hget("confirming_payments",account) or 0
    return long(balance), long(confirming)
  except Exception, e:
    log_error('RetrieveBalance: exception: %s' % str(e))
    raise

def LinkCore(link,other_identity):
  try:
    identity=link.identity()
    if identity==other_identity:
      return True, "same-identity"
    links=redis_hget('links',identity)
    if links:
      if other_identity in links.split(chr(0)):
        return True, "already"
      links=links+chr(0)+other_identity
    else:
      links=other_identity
    redis_hset('links',identity,links)

    links=redis_hget('links',other_identity)
    if links:
      if identity in links.split(chr(0)):
        # we have both
        account=GetAccount(identity)
        other_account=GetAccount(other_identity)
        if account==other_account:
          log_info('%s and %s already have the same account: %s' % (identity,other_identity,account))
          return True, "same-account"

        balance=long(redis_hget('balances',account))
        log_info('Linking accounts %s (%s) and %s (%s)' % (account,identity,other_account,other_identity))
        p=redis_pipeline()
        p.hincrby('balances',other_account,balance)
        p.hincrby('balances',account,-balance)
        accounts=redis_hgetall('accounts')
        for a in accounts:
          if accounts[a]==account:
            log_info('Changing %s\'s account from %s to %s' % (a,account,other_account))
            p.hset('accounts',a,other_account)
        p.execute()
        return True, "linked"
  except Exception,e:
    log_error('Error linking %s and %s: %s' % (identity,other_identity,str(e)))
    return False, "error"

  return True, "ok"

def IdentityFromString(link,s):
  if s.find(':') == -1:
    network = link.network
    nick=s
  else:
    parts=s.split(':')
    network_name=parts[0]
    network=GetNetworkByName(network_name)
    if not network:
      log_error('unknown network: %s' % network_name)
      raise RuntimeError('Unknown network: %s' % network_name)
    nick=parts[1]
  return network.name+':'+network.canonicalize(nick)

def NetworkFromIdentity(identity):
  return identity.split(':')[0]

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

def Lock():
  return core_lock.acquire()

def Unlock():
  core_lock.release()
  return True

