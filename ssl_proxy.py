#!/usr/bin/env python3
"""
Multi-Backend SSL Proxy (Simplified)
====================================

Uses ONLY Python standard library - no pip install required.

Features:
- Multiple backend routing based on URL path
- WebSocket support for real-time applications  
- Smart Card (client certificate) authentication as primary
- Windows Native Auth (NTLM/Kerberos) as automatic fallback
- Health checks for backends

Usage:
    python ssl_proxy_multi.py
    python ssl_proxy_multi.py --config proxy-config.yaml
    python ssl_proxy_multi.py --port 8443 --no-verify
"""

import asyncio
import base64
import json
import logging
import os
import signal
import ssl
import struct
import sys
import time
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Optional YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


BASE_DIR = os.getenv("BASE_DIR", "")
PROXY_HOST = '10.28.203.100'   # Listen on this IP
SERVER_CERT_FILE = BASE_DIR + '/controller/certs/cert.pem'       # Server certificate
SERVER_KEY_FILE = BASE_DIR + '/controller/certs/key.pem'         # Server private key
CA_CERT_FILE = BASE_DIR + '/controller/certs/certChain.pem'      # CA for client certs

# Client certificate verification
# ssl.CERT_NONE: No client certificate required
# ssl.CERT_OPTIONAL: Client can provide certificate (allows WNA fallback)
# ssl.CERT_REQUIRED: Client must provide certificate
CLIENT_CERT_REQUIRED = ssl.CERT_OPTIONAL

# Windows Native Auth configuration
ENABLE_WNA_FALLBACK = True     # Enable WNA when no client cert
WNA_SERVICE_NAME = "HTTP"      # Kerberos service name

# Headers to pass identity to backend (matching existing main.py)
CERT_CN_HEADER = "X-Client-Cert-CN"      # Certificate Common Name
CERT_DN_HEADER = "X-Client-Cert-DN"      # Certificate Distinguished Name
AUTH_METHOD_HEADER = "X-Auth-Method"     # Auth method used

# Default domain for Smart Card auth (set to your org's domain)
DEFAULT_DOMAIN = ""  # <-- CHANGE THIS to your domain (e.g., "CORP", "AGENCY")

# Logging
LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


# ============================================================================
# Configuration Classes
# ============================================================================

@dataclass
class BackendConfig:
    """Configuration for a single backend service"""
    name: str
    host: str
    port: int
    path_prefix: str = "/"
    strip_prefix: bool = True
    websocket: bool = False
    health_check_path: str = "/health"
    timeout: int = 300
    auth_required: bool = True


@dataclass  
class ProxyConfig:
    """Main proxy configuration"""
    listen_host: str = "10.28.203.100"
    listen_port: int = 7585
    ssl_cert: str = BASE_DIR + '/controller/certs/cert.pem'
    ssl_key: str = BASE_DIR + '/controller/certs/key.pem'
    ssl_ca: str = BASE_DIR + '/controller/certs/certChain.pem'
    ssl_verify_client: bool = True
    ntlm_fallback: bool = True
    ntlm_domain: str = ""
    session_timeout: int = 3600
    log_level: str = "INFO"
    log_file: str = ""
    access_log: str = ""
    backends: Dict[str, BackendConfig] = field(default_factory=dict)
    default_backend: str = ""


# ============================================================================
# Default Configuration
# ============================================================================

DEFAULT_CONFIG = ProxyConfig(
    listen_port=7585,
    backends={
        "orchestration": BackendConfig(
            name="Orchestration Dashboard",
            host="10.28.203.100",
            port=7605,
            path_prefix="/",
            strip_prefix=False,
            websocket=True,
            auth_required=True,
        ),
        "deploy-console": BackendConfig(
            name="Deployment Console",
            host="10.28.203.100",
            port=7600,
            path_prefix="/deploy",
            strip_prefix=True,
            websocket=True,
            auth_required=True,
        ),
    },
    default_backend="orchestration",
)


# ============================================================================
# Logging
# ============================================================================

def setup_logging(config: ProxyConfig) -> logging.Logger:
    logger = logging.getLogger("proxy")
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)
    
    if config.log_file:
        try:
            fh = logging.FileHandler(config.log_file)
            fh.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s'
            ))
            logger.addHandler(fh)
        except:
            pass
    
    return logger


# ============================================================================
# Authentication Manager
# ============================================================================

class AuthManager:
    """Handles Smart Card and NTLM authentication"""
    
    def __init__(self, config: ProxyConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.sessions: Dict[str, dict] = {}

    def extract_cert_user(self, ssl_obj) -> Optional[dict]:
        """Extract user from client certificate"""
        try:
            if not ssl_obj:
                return None
            cert = ssl_obj.getpeercert()
            self.logger.info(f"Certificate: {cert}")  # ADD THIS LINE
            if not cert:
                return None
            
            subject = dict(x[0] for x in cert.get('subject', []))
            cn = subject.get('commonName', '')
            
            if '\\' in cn:
                username, domain = cn.split('\\')[-1], cn.split('\\')[0]
            elif '@' in cn:
                username, domain = cn.split('@')[0], cn.split('@')[1].split('.')[0]
            else:
                username, domain = cn, ''
            
            self.logger.info(f"Cert auth: {username}")
            return {
                'auth_method': 'smartcard',
                'username': username,
                'domain': domain,
                'cn': cn,
            }
        except Exception as e:
            self.logger.debug(f"Cert extraction error: {e}")
            return None
    
    def create_ntlm_challenge(self) -> bytes:
        """Create NTLM Type 2 challenge"""
        challenge = secrets.token_bytes(8)
        target = self.config.ntlm_domain.encode('utf-16-le')
        
        msg = b'NTLMSSP\x00'  # Signature
        msg += struct.pack('<I', 2)  # Type 2
        msg += struct.pack('<HHI', len(target), len(target), 56)  # Target
        msg += struct.pack('<I', 0xe2898235)  # Flags
        msg += challenge
        msg += b'\x00' * 8  # Reserved
        msg += target
        
        return base64.b64encode(msg)
    
    def verify_ntlm(self, auth_header: str) -> Optional[dict]:
        """Verify NTLM Type 3 response"""
        try:
            if not auth_header.startswith('NTLM '):
                return None
            
            data = base64.b64decode(auth_header[5:])
            if not data.startswith(b'NTLMSSP\x00'):
                return None
            
            msg_type = struct.unpack('<I', data[8:12])[0]
            
            if msg_type == 1:
                return None  # Type 1 - need to send challenge
            
            if msg_type == 3:
                # Extract username from Type 3
                domain_len = struct.unpack('<H', data[28:30])[0]
                domain_off = struct.unpack('<I', data[32:36])[0]
                user_len = struct.unpack('<H', data[36:38])[0]
                user_off = struct.unpack('<I', data[40:44])[0]
                
                domain = data[domain_off:domain_off+domain_len].decode('utf-16-le')
                username = data[user_off:user_off+user_len].decode('utf-16-le')
                
                self.logger.info(f"NTLM auth: {domain}\\{username}")
                return {
                    'auth_method': 'ntlm',
                    'username': username,
                    'domain': domain,
                }
        except Exception as e:
            self.logger.debug(f"NTLM error: {e}")
        return None
    
    def create_session(self, user: dict) -> str:
        sid = secrets.token_urlsafe(32)
        self.sessions[sid] = {**user, 'created': time.time()}
        return sid
    
    def get_session(self, sid: str) -> Optional[dict]:
        session = self.sessions.get(sid)
        if session and time.time() - session['created'] < self.config.session_timeout:
            return session
        if sid in self.sessions:
            del self.sessions[sid]
        return None


# ============================================================================
# Backend Router
# ============================================================================

class Router:
    """Routes requests to backends based on path"""
    
    def __init__(self, config: ProxyConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        # Sort by path length (longest first)
        self.backends = sorted(
            config.backends.items(),
            key=lambda x: len(x[1].path_prefix),
            reverse=True
        )
    
    def route(self, path: str) -> Tuple[Optional[str], Optional[BackendConfig]]:
        """Find backend for path"""
        for bid, backend in self.backends:
            if path.startswith(backend.path_prefix):
                return bid, backend
        
        if self.config.default_backend:
            return (self.config.default_backend, 
                   self.config.backends.get(self.config.default_backend))
        return None, None
    
    def transform_path(self, path: str, backend: BackendConfig) -> str:
        """Transform path for backend"""
        if backend.strip_prefix:
            path = path[len(backend.path_prefix):]
            if not path.startswith('/'):
                path = '/' + path
        return path or '/'


# ============================================================================
# HTTP Utilities
# ============================================================================

def parse_request(data: bytes) -> Tuple[str, str, dict, bytes]:
    """Parse HTTP request -> (method, path, headers, body)"""
    try:
        if b'\r\n\r\n' in data:
            head, body = data.split(b'\r\n\r\n', 1)
        else:
            head, body = data, b''
        
        lines = head.decode('utf-8', errors='replace').split('\r\n')
        parts = lines[0].split(' ')
        method = parts[0]
        path = parts[1] if len(parts) > 1 else '/'
        
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        
        return method, path, headers, body
    except:
        return 'GET', '/', {}, b''


def build_response(status: int, reason: str, headers: dict, body: bytes = b'') -> bytes:
    """Build HTTP response"""
    lines = [f"HTTP/1.1 {status} {reason}"]
    if body:
        headers['Content-Length'] = str(len(body))
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    return ('\r\n'.join(lines) + '\r\n\r\n').encode() + body


def build_request(method: str, path: str, headers: dict, body: bytes = b'') -> bytes:
    """Build HTTP request"""
    lines = [f"{method} {path} HTTP/1.1"]
    for k, v in headers.items():
        lines.append(f"{k}: {v}")
    return ('\r\n'.join(lines) + '\r\n\r\n').encode() + body


# ============================================================================
# Proxy Server
# ============================================================================

class ProxyServer:
    """Main proxy server"""
    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.logger = setup_logging(config)
        self.auth = AuthManager(config, self.logger)
        self.router = Router(config, self.logger)
    
    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle client connection"""
        addr = writer.get_extra_info('peername')
        ssl_obj = writer.get_extra_info('ssl_object')
        
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not data:
                return
            
            method, path, headers, body = parse_request(data)
            
            # Route to backend
            bid, backend = self.router.route(path)
            if not backend:
                writer.write(build_response(404, 'Not Found', {}, b'No route'))
                await writer.drain()
                return
            
            # Authentication
            user = None
            if backend.auth_required:
                # Try cert first
                user = self.auth.extract_cert_user(ssl_obj)
                
                # Try NTLM fallback
                if not user and self.config.ntlm_fallback:
                    # Check session cookie
                    cookies = headers.get('cookie', '')
                    for c in cookies.split(';'):
                        if 'proxy_session=' in c:
                            sid = c.split('=')[1].strip()
                            user = self.auth.get_session(sid)
                            break
                    
                    if not user:
                        auth = headers.get('authorization', '')
                        if auth.startswith('NTLM '):
                            user = self.auth.verify_ntlm(auth)
                            if not user:
                                # Send challenge
                                challenge = self.auth.create_ntlm_challenge()
                                resp = build_response(401, 'Unauthorized', {
                                    'WWW-Authenticate': f'NTLM {challenge.decode()}',
                                    'Connection': 'keep-alive'
                                })
                                writer.write(resp)
                                await writer.drain()
                                return
                        else:
                            # Request NTLM
                            resp = build_response(401, 'Unauthorized', {
                                'WWW-Authenticate': 'NTLM',
                                'Connection': 'keep-alive'
                            })
                            writer.write(resp)
                            await writer.drain()
                            return
                
                if not user:
                    writer.write(build_response(401, 'Unauthorized', {}, b'Auth required'))
                    await writer.drain()
                    return
            
            # Connect to backend
            try:
                br, bw = await asyncio.wait_for(
                    asyncio.open_connection(backend.host, backend.port),
                    timeout=10
                )
            except Exception as e:
                self.logger.error(f"Backend error: {e}")
                writer.write(build_response(502, 'Bad Gateway', {}, b'Backend down'))
                await writer.drain()
                return
            
            try:
                # Transform path
                bpath = self.router.transform_path(path, backend)
                
                # Build backend request
                bheaders = dict(headers)
                bheaders['host'] = f"{backend.host}:{backend.port}"
                if user:
                    bheaders['x-authenticated-user'] = user.get('username', '')
                    bheaders['x-auth-method'] = user.get('auth_method', '')
                    bheaders['x-user-domain'] = user.get('domain', '')
                
                # Remove hop headers
                for h in ['connection', 'keep-alive', 'upgrade', 'proxy-authorization']:
                    bheaders.pop(h, None)
                
                # Check WebSocket
                is_ws = (backend.websocket and 
                        'websocket' in headers.get('upgrade', '').lower())
                
                if is_ws:
                    # Keep upgrade headers for WebSocket
                    bheaders['upgrade'] = headers.get('upgrade', '')
                    bheaders['connection'] = headers.get('connection', '')
                    if 'sec-websocket-key' in headers:
                        bheaders['sec-websocket-key'] = headers['sec-websocket-key']
                    if 'sec-websocket-version' in headers:
                        bheaders['sec-websocket-version'] = headers['sec-websocket-version']
                
                # Send to backend
                req = build_request(method, bpath, bheaders, body)
                bw.write(req)
                await bw.drain()
                
                if is_ws:
                    # Forward WebSocket upgrade response
                    resp = await br.read(4096)
                    writer.write(resp)
                    await writer.drain()
                    
                    if b'101' in resp[:50]:
                        # Proxy WebSocket bidirectionally
                        await self._proxy_ws(reader, writer, br, bw)
                else:
                    # Forward HTTP response
                    while True:
                        chunk = await asyncio.wait_for(br.read(65536), timeout=backend.timeout)
                        if not chunk:
                            break
                        writer.write(chunk)
                        await writer.drain()
                        
            finally:
                bw.close()
                
            self.logger.info(f"{addr} {method} {path} -> {bid}")
            
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout: {addr}")
        except Exception as e:
            self.logger.error(f"Error: {e}")
        finally:
            writer.close()
    
    async def _proxy_ws(self, cr, cw, br, bw):
        """Bidirectional WebSocket proxy"""
        async def fwd(r, w):
            try:
                while True:
                    data = await r.read(65536)
                    if not data:
                        break
                    w.write(data)
                    await w.drain()
            except:
                pass
        
        t1 = asyncio.create_task(fwd(cr, bw))
        t2 = asyncio.create_task(fwd(br, cw))
        
        done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    
    def _create_ssl_context(self) -> ssl.SSLContext:
        """Create SSL context"""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        
        if not os.path.exists(self.config.ssl_cert):
            raise FileNotFoundError(f"SSL cert not found: {self.config.ssl_cert}")
        if not os.path.exists(self.config.ssl_key):
            raise FileNotFoundError(f"SSL key not found: {self.config.ssl_key}")
        
        ctx.load_cert_chain(self.config.ssl_cert, self.config.ssl_key)
        
        if self.config.ssl_verify_client:
            ctx.verify_mode = ssl.CERT_OPTIONAL
            if os.path.exists(self.config.ssl_ca):
                ctx.load_verify_locations(self.config.ssl_ca)
        else:
            ctx.verify_mode = ssl.CERT_NONE
        
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx
    
    async def start(self):
        """Start server"""
        ctx = self._create_ssl_context()
        
        server = await asyncio.start_server(
            self.handle,
            self.config.listen_host,
            self.config.listen_port,
            ssl=ctx
        )
        
        print("=" * 60)
        print("Multi-Backend SSL Proxy")
        print("=" * 60)
        print(f"Listening: https://{self.config.listen_host}:{self.config.listen_port}")
        print(f"Client certs: {'Optional' if self.config.ssl_verify_client else 'Disabled'}")
        print(f"NTLM fallback: {self.config.ntlm_fallback}")
        print("-" * 60)
        print("Backends:")
        for bid, b in self.config.backends.items():
            flags = []
            if b.websocket: flags.append("WS")
            if b.auth_required: flags.append("Auth")
            print(f"  {b.path_prefix:15} -> {b.host}:{b.port} [{', '.join(flags)}]")
        print("=" * 60)
        
        async with server:
            await server.serve_forever()


# ============================================================================
# Config Loading
# ============================================================================

BASE_DIR = os.getenv("BASE_DIR", "")
PROXY_HOST = '10.28.203.100'   # Listen on this IP
SERVER_CERT_FILE = BASE_DIR + '/controller/certs/cert.pem'       # Server certificate
SERVER_KEY_FILE = BASE_DIR + '/controller/certs/key.pem'         # Server private key
CA_CERT_FILE = BASE_DIR + '/controller/certs/certChain.pem'      # CA for client certs


def load_config(path: Optional[str]) -> ProxyConfig:
    """Load config from YAML or use defaults"""
    if path and os.path.exists(path) and YAML_AVAILABLE:
        with open(path) as f:
            data = yaml.safe_load(f)
        

        config = ProxyConfig(
            listen_host=data.get('listen_host', '10.28.203.100'),
            listen_port=data.get('listen_port', 7585),
            ssl_cert=data.get('ssl_cert', BASE_DIR + '/controller/certs/cert.pem'),
            ssl_key=data.get('ssl_key', BASE_DIR + '/controller/certs/key.pem'),
            ssl_ca=data.get('ssl_ca', BASE_DIR + '/controller/certs/certChain.pem'),
            ssl_verify_client=data.get('ssl_verify_client', True),
            ntlm_fallback=data.get('ntlm_fallback', True),
            ntlm_domain=data.get('ntlm_domain', ''),
            session_timeout=data.get('session_timeout', 3600),
            log_level=data.get('log_level', 'DEBUG'),
            default_backend=data.get('default_backend', ''),
        )
        
        for bid, bdata in data.get('backends', {}).items():
            config.backends[bid] = BackendConfig(
                name=bdata.get('name', bid),
                host=bdata.get('host', '10.28.203.100'),
                port=bdata.get('port', 8000),
                path_prefix=bdata.get('path_prefix', '/'),
                strip_prefix=bdata.get('strip_prefix', True),
                websocket=bdata.get('websocket', False),
                timeout=bdata.get('timeout', 300),
                auth_required=bdata.get('auth_required', True),
            )
        
        return config
    
    return DEFAULT_CONFIG


# ============================================================================
# Main
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Multi-Backend SSL Proxy')
    parser.add_argument('--config', '-c', help='YAML config file')
    parser.add_argument('--port', '-p', type=int, help='Listen port')
    parser.add_argument('--host', '-H', help='Listen host')
    parser.add_argument('--cert', help='SSL certificate')
    parser.add_argument('--key', help='SSL private key')
    parser.add_argument('--no-verify', action='store_true', help='Disable client cert verification')
    args = parser.parse_args()
    
    config = load_config(args.config)
    
    if args.port: config.listen_port = args.port
    if args.host: config.listen_host = args.host
    if args.cert: config.ssl_cert = args.cert
    if args.key: config.ssl_key = args.key
    if args.no_verify: config.ssl_verify_client = False
    
    proxy = ProxyServer(config)
    
    def shutdown(sig, frame):
        print("\nShutting down...")
        sys.exit(0)
    
    #signal.signal(signal.SIGINT, shutdown)
    #signal.signal(signal.SIGTERM, shutdown)
    
    try:
        asyncio.run(proxy.start())
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("\nGenerate test certs with:")
        print("  openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes")
        sys.exit(1)


if __name__ == '__main__':
    main()

