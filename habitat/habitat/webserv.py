#! /usr/bin/env python
# cgiserver.py
#http://mail.python.org/pipermail/tutor/2005-November/043202.html

import posixpath, sys, os, urllib, select

from BaseHTTPServer import HTTPServer
from CGIHTTPServer import CGIHTTPRequestHandler
from SocketServer import ThreadingMixIn

class ThreadingServer(ThreadingMixIn, HTTPServer):
    pass

class MyRequestHandler(CGIHTTPRequestHandler):
    '''I could not figure out how to convince the Python os.stat module
    that the perl scripts are executable so that the server would actually
    run them.  The simple solution is to override is_executable to always
    return true.  (The perl scripts are indeed executable and do run.)
    '''
    def is_executable(self, path):
        return True


serveraddr = ('',51712)
srvr = ThreadingServer(serveraddr, MyRequestHandler)
srvr.serve_forever()

