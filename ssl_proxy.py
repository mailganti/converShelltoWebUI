#!/usr/bin/env python3
"""
Multi-Backend SSL Proxy
=======================

All configuration is loaded from proxy-config.yaml

Features:
- Multiple backend routing based on URL path
- WebSocket support for real-time applications
- Smart Card (client certificate) authentication
- Windows Native Auth (NTLM/Kerberos) fallback
- All settings configurable via YAML

Usage:
    python ssl_proxy_multi.py --config proxy-config.yaml
"""

import asyncio
import base64
import logging
import os
import re
import signal
import ssl
import struct
import sys
import time
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Tuple

# Certificate parsing with cryptography library
try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    print("WARNING: cryptography not installed. Install with: pip install cryptography")

# YAML support
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("ERROR: PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)


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
    timeout: int = 300
    auth_required: bool = True


@dataclass
class ProxyConfig:
    """Main proxy configuration - loaded from YAML"""
    # Server
    listen_host: str = "0.0.0.0"
    listen_port: int = 8443
    
    # SSL
    ssl_cert: str = ""
    ssl_key: str = ""
    ssl_ca: str = ""
    ssl_verify_client: bool = True
    
    # Auth headers
    header_cert_cn: str = "X-Client-Cert-CN"
    header_cert_dn: str = "X-Client-Cert-DN"
    header_auth_method: str = "X-Auth-Method"
    default_domain: str = ""
    
    # NTLM
    ntlm_enabled: bool = True
    ntlm_domain: str = ""
    session_timeout: int = 3600
    
    # Logging
    log_level: str = "INFO"
    log_file: str = ""
    access_log: str = ""
    
    # Backends
    backends: Dict[str, BackendConfig] = field(default_factory=dict)
    default_backend: str = ""
    
    # Advanced
    read_buffer: int = 65536


# ============================================================================
# Environment Variable Expansion
# ============================================================================

def expand_env_vars(value: str) -> str:
    """Expand ${VAR} and $VAR in strings"""
    if not isinstance(value, str):
        return value
    
    # Expand ${VAR} format
    pattern = re.compile(r'\$\{([^}]+)\}')
    def replace(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    
    result = pattern.sub(replace, value)
    
    # Expand $VAR format (word boundary)
    pattern2 = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)')
    def replace2(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))
    
    return pattern2.sub(replace2, result)


# ============================================================================
# Configuration Loading
# ============================================================================

def load_config(config_path: str) -> ProxyConfig:
    """Load configuration from YAML file"""
    
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    
    with open(config_path) as f:
        data = yaml.safe_load(f)
    
    # Extract sections with defaults
    server = data.get('server', {})
    ssl_config = data.get('ssl', {})
    auth = data.get('auth', {})
    auth_headers = auth.get('headers', {})
    ntlm = auth.get('ntlm', {})
    logging_config = data.get('logging', {})
    advanced = data.get('advanced', {})
    
    # Build config object
    config = ProxyConfig(
        # Server
        listen_host=server.get('host', '0.0.0.0'),
        listen_port=server.get('port', 8443),
        
        # SSL - expand environment variables
        ssl_cert=expand_env_vars(ssl_config.get('cert', '')),
        ssl_key=expand_env_vars(ssl_config.get('key', '')),
        ssl_ca=expand_env_vars(ssl_config.get('ca', '')),
        ssl_verify_client=ssl_config.get('verify_client', True),
        
        # Auth headers
        header_cert_cn=auth_headers.get('cert_cn', 'X-Client-Cert-CN'),
        header_cert_dn=auth_headers.get('cert_dn', 'X-Client-Cert-DN'),
        header_auth_method=auth_headers.get('auth_method', 'X-Auth-Method'),
        default_domain=auth.get('default_domain', ''),
        
        # NTLM
        ntlm_enabled=ntlm.get('enabled', True),
        ntlm_domain=ntlm.get('domain', ''),
        session_timeout=auth.get('session_timeout', 3600),
        
        # Logging - expand environment variables
        log_level=logging_config.get('level', 'INFO'),
        log_file=expand_env_vars(logging_config.get('file', '')),
        access_log=expand_env_vars(logging_config.get('access_log', '')),
        
        # Default backend
        default_backend=data.get('default_backend', ''),
        
        # Advanced
        read_buffer=advanced.get('read_buffer', 65536),
    )
    
    # Parse backends
    for bid, bdata in data.get('backends', {}).items():
        config.backends[bid] = BackendConfig(
            name=bdata.get('name', bid),
            host=bdata.get('host', 'localhost'),
            port=bdata.get('port', 8000),
            path_prefix=bdata.get('path_prefix', '/'),
            strip_prefix=bdata.get('strip_prefix', True),
            websocket=bdata.get('websocket', False),
            timeout=bdata.get('timeout', 300),
            auth_required=bdata.get('auth_required', True),
        )
    
    return config


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(config: ProxyConfig) -> logging.Logger:
    """Configure logging based on config"""
    logger = logging.getLogger("proxy")
    logger.setLevel(getattr(logging, config.log_level.upper(), logging.INFO))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(handler)
    
    # File handler
    if config.log_file:
        try:
            # Ensure directory exists
            log_dir = os.path.dirname(config.log_file)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            fh = logging.FileHandler(config.log_file)
            fh.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s'
            ))
            logger.addHandler(fh)
        except Exception as e:
            print(f"Warning: Could not create log file: {e}")
    
    return logger


# ============================================================================
# Certificate Parsing
# ============================================================================

def extract_cert_identity(cert_der: bytes, logger) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract identity from client certificate using cryptography library.
    
    Returns: (cn, domain, cert_dn)
    """
    if not CRYPTO_AVAILABLE:
        logger.error("cryptography library not available")
        return None, None, None
    
    try:
        cert = x509.load_der_x509_certificate(cert_der, default_backend())
        subject = cert.subject
        
        # Extract Common Name
        cn = None
        for attr in subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                cn = attr.value
                break
        
        # Build DN string
        dn_parts = []
        for attr in subject:
            dn_parts.append(f"{attr.oid._name}={attr.value}")
        cert_dn = ", ".join(dn_parts)
        
        return cn, None, cert_dn
        
    except Exception as e:
        logger.error(f"Error parsing certificate: {e}")
        return None, None, None


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
            
            # Get certificate in DER (binary) format
            cert_der = ssl_obj.getpeercert(binary_form=True)
            if not cert_der:
                self.logger.debug("No client certificate provided")
                return None
            
            # Parse certificate
            cn, _, cert_dn = extract_cert_identity(cert_der, self.logger)
            
            if not cn:
                self.logger.warning("Could not extract CN from certificate")
                return None
            
            self.logger.info(f"Smart Card auth: {cn}")
            
            return {
                'auth_method': 'smartcard',
                'cn': cn,
                'cert_dn': cert_dn,
                'domain': self.config.default_domain,
            }
            
        except Exception as e:
            self.logger.error(f"Cert extraction error: {e}")
            return None
    
    def create_ntlm_challenge(self) -> bytes:
        """Create NTLM Type 2 challenge"""
        challenge = secrets.token_bytes(8)
        target = self.config.ntlm_domain.encode('utf-16-le')
        
        msg = b'NTLMSSP\x00'
        msg += struct.pack('<I', 2)
        msg += struct.pack('<HHI', len(target), len(target), 56)
        msg += struct.pack('<I', 0xe2898235)
        msg += challenge
        msg += b'\x00' * 8
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
                    'cn': username,
                    'domain': domain,
                    'cert_dn': f"CN={username}",
                }
        except Exception as e:
            self.logger.debug(f"NTLM error: {e}")
        return None
    
    def create_session(self, user: dict) -> str:
        """Create authenticated session"""
        sid = secrets.token_urlsafe(32)
        self.sessions[sid] = {**user, 'created': time.time()}
        return sid
    
    def get_session(self, sid: str) -> Optional[dict]:
        """Get session if valid"""
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
        
        self.logger.debug(f"[1] New connection from {addr}")
        
        try:
            data = await asyncio.wait_for(
                reader.read(self.config.read_buffer),
                timeout=30
            )
            if not data:
                self.logger.debug(f"[2] No data received, closing")
                return
            
            self.logger.debug(f"[2] Received {len(data)} bytes")
            
            method, path, headers, body = parse_request(data)
            self.logger.debug(f"[3] Parsed: {method} {path}")
            
            # Route to backend
            bid, backend = self.router.route(path)
            if not backend:
                self.logger.warning(f"[4] No route for {path}")
                writer.write(build_response(404, 'Not Found', {}, b'No route'))
                await writer.drain()
                return
            
            self.logger.debug(f"[4] Routed to backend: {bid} ({backend.host}:{backend.port})")
            
            # Authentication
            user = None
            if backend.auth_required:
                # Try cert first
                self.logger.debug(f"[5] Attempting cert auth...")
                user = self.auth.extract_cert_user(ssl_obj)
                
                # Try NTLM fallback
                if not user and self.config.ntlm_enabled:
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
                    self.logger.warning(f"[6] Auth failed - no user")
                    writer.write(build_response(401, 'Unauthorized', {}, b'Auth required'))
                    await writer.drain()
                    return
            
            self.logger.debug(f"[6] Auth success: {user.get('cn', 'unknown')}")
            
            # Connect to backend
            self.logger.debug(f"[7] Connecting to backend {backend.host}:{backend.port}...")
            try:
                br, bw = await asyncio.wait_for(
                    asyncio.open_connection(backend.host, backend.port),
                    timeout=10
                )
                self.logger.debug(f"[7] Backend connected successfully")
            except Exception as e:
                self.logger.error(f"[7] Backend connection FAILED: {e}")
                writer.write(build_response(502, 'Bad Gateway', {}, b'Backend unavailable'))
                await writer.drain()
                return
            
            try:
                # Transform path
                bpath = self.router.transform_path(path, backend)
                
                # Build backend request headers
                bheaders = dict(headers)
                bheaders['host'] = f"{backend.host}:{backend.port}"
                
                # Add auth headers using configured header names
                if user:
                    bheaders[self.config.header_cert_cn] = user.get('cn', '')
                    bheaders[self.config.header_auth_method] = user.get('auth_method', '')
                    if user.get('cert_dn'):
                        bheaders[self.config.header_cert_dn] = user.get('cert_dn', '')
                    # Add forwarding headers
                    bheaders['X-Forwarded-For'] = addr[0] if addr else ''
                    bheaders['X-Forwarded-Proto'] = 'https'
                
                # Check WebSocket first
                is_ws = (backend.websocket and
                        'websocket' in headers.get('upgrade', '').lower())
                
                # Remove hop headers (but keep connection for HTTP/1.1)
                for h in ['keep-alive', 'upgrade', 'proxy-authorization', 'authorization']:
                    bheaders.pop(h, None)
                
                # Ensure connection header for HTTP/1.1
                if not is_ws:
                    bheaders['connection'] = 'close'
                
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
                self.logger.debug(f"[8] Sending request to backend: {method} {bpath}")
                self.logger.debug(f"[8] Headers: {list(bheaders.keys())}")
                
                # Log the actual request (first 500 bytes)
                req_preview = req[:500].decode('utf-8', errors='replace')
                self.logger.debug(f"[8] Request:\n{req_preview}")
                
                bw.write(req)
                await bw.drain()
                self.logger.debug(f"[8] Request sent ({len(req)} bytes), waiting for response...")
                
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
                    first_chunk = True
                    total_bytes = 0
                    self.logger.debug(f"[9] Reading response from backend...")
                    while True:
                        try:
                            chunk = await asyncio.wait_for(
                                br.read(self.config.read_buffer),
                                timeout=backend.timeout
                            )
                        except Exception as read_err:
                            self.logger.error(f"[9] Read error: {read_err}")
                            break
                            
                        if not chunk:
                            self.logger.debug(f"[9] Backend closed connection (EOF)")
                            break
                        if first_chunk:
                            # Log first line of response
                            first_line = chunk.split(b'\r\n')[0].decode('utf-8', errors='replace')
                            self.logger.debug(f"[9] Response: {first_line}")
                            self.logger.debug(f"[9] First chunk size: {len(chunk)} bytes")
                            first_chunk = False
                        total_bytes += len(chunk)
                        writer.write(chunk)
                        await writer.drain()
                    
                    self.logger.debug(f"[10] Forwarded {total_bytes} bytes to client")
                        
            finally:
                bw.close()
                
            self.logger.info(f"{addr} {method} {path} -> {bid}")
            
        except asyncio.TimeoutError:
            self.logger.error(f"TIMEOUT: {addr}")
        except Exception as e:
            self.logger.error(f"EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
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
        
        # Verify cert files exist
        if not os.path.exists(self.config.ssl_cert):
            raise FileNotFoundError(f"SSL cert not found: {self.config.ssl_cert}")
        if not os.path.exists(self.config.ssl_key):
            raise FileNotFoundError(f"SSL key not found: {self.config.ssl_key}")
        
        # Load server certificate
        ctx.load_cert_chain(self.config.ssl_cert, self.config.ssl_key)
        print(f"✓ Server cert: {self.config.ssl_cert}")
        
        # Client certificate verification
        if self.config.ssl_verify_client:
            if os.path.exists(self.config.ssl_ca):
                ctx.load_verify_locations(self.config.ssl_ca)
                ctx.verify_mode = ssl.CERT_OPTIONAL
                print(f"✓ CA cert: {self.config.ssl_ca}")
                print(f"✓ Client cert verification: ENABLED")
            else:
                print(f"⚠ CA cert not found: {self.config.ssl_ca}")
                print(f"⚠ Client cert verification: DISABLED")
                ctx.verify_mode = ssl.CERT_NONE
        else:
            ctx.verify_mode = ssl.CERT_NONE
            print(f"✓ Client cert verification: DISABLED (config)")
        
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
        print(f"NTLM fallback: {self.config.ntlm_enabled}")
        print("-" * 60)
        print("Auth Headers:")
        print(f"  CN Header:     {self.config.header_cert_cn}")
        print(f"  DN Header:     {self.config.header_cert_dn}")
        print(f"  Method Header: {self.config.header_auth_method}")
        print("-" * 60)
        print("Backends:")
        for bid, b in self.config.backends.items():
            flags = []
            if b.websocket: flags.append("WS")
            if b.auth_required: flags.append("Auth")
            print(f"  {b.path_prefix:15} -> {b.host}:{b.port} [{', '.join(flags)}]")
        print("=" * 60)
        
        if self.config.log_file:
            print(f"Logging to: {self.config.log_file}")
        
        async with server:
            await server.serve_forever()


# ============================================================================
# Main
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Multi-Backend SSL Proxy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python ssl_proxy_multi.py --config proxy-config.yaml
    python ssl_proxy_multi.py -c /path/to/config.yaml

All configuration is done via the YAML file.
        """
    )
    parser.add_argument('--config', '-c', required=True, help='YAML config file (required)')
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Create and start proxy
    proxy = ProxyServer(config)
    
    def shutdown(sig, frame):
        print("\nShutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    try:
        asyncio.run(proxy.start())
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
