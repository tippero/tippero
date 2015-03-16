#!/bin/python
#
# Cryptonote tipbot - Twitter
# Copyright 2015 moneromooo
#
# The Cryptonote tipbot is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2, or (at your option)
# any later version.
#

import sys
import os
import string
import time
import threading
import re
import hashlib
import time
from Crypto.Random.random import getrandbits
import tweepy
import tipbot.config as config
from tipbot.log import log_error, log_warn, log_info, log_log
from tipbot.user import User
from tipbot.link import Link
from tipbot.utils import *
from tipbot.command_manager import *
from tipbot.network import *

amount_regexp="\+[0-9]*\.[0-9]*"
username_regexp="@[a-zA-Z0-9_]+|[a-zA-Z]+:[a-zA-Z0-9]+"

force_parse_self = False

class TwitterNetwork(Network):
  def __init__(self,name):
    Network.__init__(self,name)
    self.last_update_time=0
    self.last_seen_tweet_id=None
    self.last_seen_dm_id=None
    self.thread=None

  def is_identified(self,link):
    # all twitter users are identified
    return True

  def connect(self):
    if self.thread:
      return False
    try:
      cfg=config.network_config[self.name]
      self.login=cfg['login']
      ckey=GetPassword(self.name+"/ckey")
      csecret=GetPassword(self.name+"/csecret")
      atoken=GetPassword(self.name+"/atoken")
      atsecret=GetPassword(self.name+"/atsecret")
      self.update_period=cfg['update_period']
      self.keyword=cfg['keyword'].lower()
      self.fs_location=cfg['fs_location']
      self.fs_prefix_tree=cfg['fs_prefix_tree']
      self.uri_base=cfg['uri_base']

      if self.fs_location and not self._is_valid_location(self.fs_location):
        log_error('Invalid location: %s' % self.fs_location)
        return False

      self.items_cache=dict()
      self.last_seen_tweet_id=long(redis_get('twitter:last_seen_tweet_id') or 0)
      self.last_seen_dm_id=long(redis_get('twitter:last_seen_dm_id') or 0)
      log_log('loaded last seen id: tweet %s, dm %s' % (str(self.last_seen_tweet_id),str(self.last_seen_dm_id)))

      auth=tweepy.OAuthHandler(ckey,csecret)
      auth.set_access_token(atoken,atsecret)
      self.twitter=tweepy.API(auth)

      self.stop = False
      self.thread = threading.Thread(target=self.run)
      self.thread.start()

    except Exception,e:
      log_error('Failed to login to twitter: %s' % str(e))
      return False
    return True

  def disconnect(self):
    log_info('Twitter disconnect')
    if not self.thread:
      return
    log_info('Shutting down Twitter thread')
    self.stop = True
    self.thread.join()
    self.thread = None
    self.items_cache=None
    self.last_seen_tweet_id=None
    self.last_seen_dm_id=None
    self.twitter = None

  def send_group(self,group,msg,data=None):
    return self._schedule_tweet(msg,data)

  def send_user(self,user,msg,data=None):
    if data:
      # msg to reply to -> tweet
      return self._schedule_tweet(msg,data)
    else:
      return self._schedule_dm(msg,user)

  def _schedule_tweet(self,msg,reply_to_msg):
    try:
      log_info('Scheduling tweet in reply to %s: %s' % (str(reply_to_msg.id),msg))
      if self.uri_base:
        uri=self._make_uri(msg)
        name=self.canonicalize(reply_to_msg.user.screen_name)
        msg="%s: %s" % (name,uri)
      reply="g:"+str(reply_to_msg.id)+":"+msg
      redis_rpush('twitter:replies',reply)
    except Exception,e:
      log_error('Error scheduling tweet: %s' % str(e))

  def _schedule_dm(self,msg,user):
    try:
      log_info('Scheduling DM to %s: %s' % (str(user.nick),msg))
      if self.uri_base:
        uri=self._make_uri(msg)
        nick=self.canonicalize(user.nick)
        msg="%s: %s" % (nick,uri)
      reply="u:"+str(user.nick)+":"+msg
      redis_rpush('twitter:replies',reply)
    except Exception,e:
      log_error('Error scheduling DM: %s' % str(e))


  def is_acceptable_command_prefix(self,s):
    s=s.strip()
    if s=="":
      return True
    if s.lower() == self.keyword:
      return True
    return False

  def _parse_dm(self,msg):
    if msg.sender.screen_name.lower() == self.login.lower() and not force_parse_self:
      log_log('Ignoring DM from self')
      return

    log_info('Twitter: parsing DM from %s: %s' % (msg.sender.screen_name,msg.text))
    link=Link(self,User(self,msg.sender.screen_name),None,None)
    for line in msg.text.split('\n'):
      exidx=line.find('!')
      if exidx!=-1 and len(line)>exidx+1 and line[exidx+1] in string.ascii_letters and self.is_acceptable_command_prefix(line[:exidx]):
        cmd=line[exidx+1:].split(' ')
        cmd[0] = cmd[0].strip(' \t\n\r')
        log_info('Found command from %s: %s' % (link.identity(), str(cmd)))
        if self.on_command:
          self.on_command(link,cmd)

  def _parse_tweet(self,msg):
    if msg.user.screen_name.lower() == self.login.lower() and not force_parse_self:
      log_log('Ignoring tweet from self')
      return

    log_info('Twitter: parsing tweet from %s: %s' % (msg.user.screen_name,msg.text))

    # twitter special: +x means tip the user mentioned with a @
    for line in msg.text.split('\n'):
      line=line.lower()
      line=line.replace(self.keyword,'',1).strip()
      log_log('After removal: %s' % line)
      if re.match(username_regexp+"[ \t]*"+amount_regexp,line) or re.match(amount_regexp+"[ \t]*"+username_regexp,line):
        link=Link(self,User(self,msg.user.screen_name),None,msg)
        match=re.search(username_regexp,line)
        if not match:
          continue
        target=match.group(0)
        if self.on_command:
          try:
            synthetic_cmd=['tip',target,line.replace('+','').replace(target,'').strip()]
            log_log('Running synthetic command: %s' % (str(synthetic_cmd)))
            self.on_command(link,synthetic_cmd)
          except Exception,e:
            log_error('Failed to tip %s: %s' % (target,str(e)))

  def _post_next_reply(self):
    data=redis_lindex('twitter:replies',0)
    if not data:
      return False
    parts=data.split(':',2)
    mtype=parts[0]
    data=parts[1]
    text=parts[2]

    try:
      if mtype == 'g':
        log_info('call: update_status(%s,%s)' % (str(text),str(data)))
        self.twitter.update_status(text,data)
      elif mtype == 'u':
        log_info('call: send_direct_message(%s,%s)' % (str(data),str(text)))
        self.twitter.send_direct_message(user=data,text=text)
      else:
        log_error('Invalid reply type: %s' % str(mtype))
      redis_lpop('twitter:replies')
    except Exception,e:
      log_error('Failed to send reply: %s' % str(e))
      redis_lpop('twitter:replies')
      return True

      return False

    return True

  def canonicalize(self,name):
    if not name.startswith('@'):
      name='@'+name
    return name.lower()

  def update(self):
    return True

  def _check(self):
    now=time.time()
    if now-self.last_update_time < self.update_period:
      return True
    self.last_update_time=now

    if True:
      results = self.twitter.direct_messages(since_id=self.last_seen_dm_id)
      for result in results:
        self._parse_dm(result)
        if long(result.id) > self.last_seen_dm_id:
          self.last_seen_dm_id = long(result.id)
          redis_set('twitter:last_seen_dm_id',self.last_seen_dm_id)

    # doesn't seem to obey since_id
    #results = self.twitter.mentions_timeline(since_id=self.last_seen_tweet_id)
    results = [status for status in tweepy.Cursor(self.twitter.mentions_timeline,q=self.keyword,since_id=self.last_seen_tweet_id).items(100)]
    for result in results:
      self._parse_tweet(result)
      if long(result.id) > self.last_seen_tweet_id:
        self.last_seen_tweet_id = long(result.id)
        redis_set('twitter:last_seen_tweet_id',self.last_seen_tweet_id)

    while self._post_next_reply():
      pass

    log_log('TwitterNetwork: update done in %.1f seconds' % float(time.time()-self.last_update_time))
    return True

  def run(self):
    while not self.stop:
      try:
        self._check()
      except Exception,e:
        log_error('Exception in TwitterNetwork:_check: %s' % str(e))
      time.sleep(1)

  def _is_valid_location(self,location):
    try:
      path=os.path.abspath(location)
      if not os.path.exists(path):
        log_error('Path %s does not exist' % str(path))
        return False
      if not os.path.isdir(path):
        log_error('%s is not a directory' % str(path))
        return False
      return True
    except Exception,e:
      log_error('Error checking path %s: %s' % (str(location),str(e)))
      return False

  def _check_and_create(self,filename,contents):
    if len(filename)<=self.fs_prefix_tree:
      log_error('Filename %s too small for prefix tree %d' % (filename,self.fs_prefix_tree))
      return None
    path=self.fs_location
    split_path=''
    for p in range(self.fs_prefix_tree):
      path=os.path.join(path,filename[p])
      split_path='/'.join([split_path,filename[p]])
      if os.path.exists(path):
        if not os.path.isdir(path):
          log_log('notadir')
          log_error('%s exists and is not a directory' % str(path))
          return None
      else:
        os.mkdir(path)
    fpath=os.path.join(path,filename[self.fs_prefix_tree:])
    split_path='/'.join([split_path,filename[self.fs_prefix_tree:]])
    if os.path.exists(fpath):
      log_error('%s exists' % str(fpath))
      return None
    f=open(fpath,'w')
    f.write(contents)
    f.close()
    return split_path

  def _intern(self,contents):
    base=str(time.time())+":"+str(getrandbits(128))+":"
    for n in range(10000):
      filename=hashlib.sha256(base+str(n)).hexdigest()
      split_path=self._check_and_create(filename,contents)
      if split_path:
        return split_path
    log_error('Failed to intern contents')
    return None

  def _make_uri(self,contents):
    filename = self._intern(contents)
    if not filename:
      return None
    return self.uri_base.rstrip("/") + "/" + filename.lstrip("/")

RegisterNetwork("twitter",TwitterNetwork)
