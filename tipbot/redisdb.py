#!/bin/python
#
# Cryptonote tipbot
# Copyright 2014 moneromooo
# Inspired by "Simple Python IRC bot" by berend
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import redis
from tipbot.log import log_error, log_warn, log_info, log_log

redisdb = None

def connect_to_redis(host,port):
  log_info('Connecting to Redis at %s:%u' % (host, port))
  try:
    global redisdb
    redisdb = redis.Redis(host=host,port=port)
    return redisdb
  except Exception, e:
    log_error( 'Error initializing redis: %s' % str(e))
    exit()

def redis_pipeline():
  return redisdb.pipeline()

def redis_exists(k):
  return redisdb.exists(k)

def redis_get(k):
  return redisdb.get(k)

def redis_set(k,v):
  return redisdb.set(k,v)

def redis_hexists(t,k):
  return redisdb.hexists(t,k)

def redis_hget(t,k):
  return redisdb.hget(t,k)

def redis_hgetall(t):
  return redisdb.hgetall(t)

def redis_hset(t,k,v):
  return redisdb.hset(t,k,v)

def redis_hincrby(t,k,v):
  return redisdb.hincrby(t,k,v)

def redis_hdel(t,k):
  return redisdb.hdel(t,k)

def redis_incrby(k,v):
  return redisdb.incrby(k,v)

def redis_sadd(k,v):
  return redisdb.sadd(k,v)

def redis_smembers(k):
  return redisdb.smembers(k)

def redis_sismember(k,v):
  return redisdb.sismember(k,v)

def redis_rpush(k,v):
  return redisdb.rpush(k,v)

def redis_lpop(k):
  return redisdb.lpop(k)

def redis_lindex(k,n):
  return redisdb.lindex(k,n)

def redis_zincrby(t,k,s):
  return redisdb.zincrby(t,k,s)

def redis_zscore(t,k):
  return redisdb.zscore(t,k)

def redis_zrangebylex(t,x0,x1):
  return redisdb.zrangebylex(t,x0,x1)

def redis_keys(s):
  return redisdb.keys(s)

def redis_delete(k):
  return redisdb.delete(k)


def CompatibilityCheck():
  try:
    r = redis.Redis()
    if not r.pipeline: raise RuntimeError('pipeline call not found')
    p = r.pipeline()
    if not p.exists: raise RuntimeError('exists call not found')
    if not p.get: raise RuntimeError('get call not found')
    if not p.set: raise RuntimeError('set call not found')
    if not p.hexists: raise RuntimeError('hexists call not found')
    if not p.hget: raise RuntimeError('hget call not found')
    if not p.hgetall: raise RuntimeError('hgetall call not found')
    if not p.hset: raise RuntimeError('hset call not found')
    if not p.hincrby: raise RuntimeError('hincrby call not found')
    if not p.hdel: raise RuntimeError('hdel call not found')
    if not p.incrby: raise RuntimeError('incrby call not found')
    if not p.sadd: raise RuntimeError('sadd call not found')
    if not p.smembers: raise RuntimeError('smembers call not found')
    if not p.sismember: raise RuntimeError('sismember call not found')
    if not p.rpush: raise RuntimeError('rpush call not found')
    if not p.lpop: raise RuntimeError('lpop call not found')
    if not p.lindex: raise RuntimeError('lindex call not found')
    if not p.zincrby: raise RuntimeError('zincrby call not found')
    if not p.zscore: raise RuntimeError('zscore call not found')
    if not p.zrangebylex: raise RuntimeError('zrangebylex call not found')
    if not p.keys: raise RuntimeError('keys call not found')
    if not p.execute: raise RuntimeError('execute call not found')
    if not p.delete: raise RuntimeError('delete call not found')
  except Exception,e:
    log_error('Error checking redis compatibility: %s' % str(e))
    exit(1)

CompatibilityCheck()

