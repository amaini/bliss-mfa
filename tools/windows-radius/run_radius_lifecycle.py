import argparse, ctypes, io, json, pathlib, re, secrets, shutil, socket, subprocess, sys, time, traceback
import pyotp
from pyrad.dictionary import Dictionary
from pyrad.packet import AuthPacket, AccessRequest, AccessAccept, AccessReject

parser=argparse.ArgumentParser(description='Disposable loopback RADIUS lifecycle validation; no Windows login changes.')
parser.add_argument('--kit-root',type=pathlib.Path,required=True,help='Extracted Bliss test kit containing work/php-runtime, work/multiotp-engine and work/multiotp-distribution')
ROOT=parser.parse_args().kit_root.resolve()
if sys.platform!='win32':parser.error('This harness requires Windows')
WORK=ROOT/'work'
for required in ['php-runtime/php.exe','php-runtime/ext','multiotp-engine/multiotp.php','multiotp-distribution/windows/radius/sbin/radiusd.exe']:
    if not (WORK/required).exists():parser.error('Missing test-kit prerequisite: '+required)
(ROOT/'outputs').mkdir(exist_ok=True)
LAB=WORK/('radius-lab-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3))
LAB.mkdir()
STATE=LAB/'engine-state'
STATE.mkdir()
PREFIX=LAB/'radius'
shutil.copytree(WORK/'multiotp-distribution/windows/radius',PREFIX)
CONF=PREFIX/'etc/raddb'
SECRET=secrets.token_urlsafe(32).encode()
RESULTS=[]
SERVER=None
LOG=None
DRIVE=None
RUNTIME_DRIVE=None
USER='bliss_radius_disposable'

def record(name,ok,evidence):
    RESULTS.append({'test':name,'passed':bool(ok),'evidence':evidence})
    print(('PASS ' if ok else 'FAIL ')+name+': '+str(evidence),flush=True)

def cli(*args):
    p=subprocess.run([str(WORK/'php-runtime/php.exe'),'-n','-d','extension_dir='+str(WORK/'php-runtime/ext'),
        '-d','extension=mbstring','-d','extension=openssl',str(WORK/'multiotp-engine/multiotp.php'),
        '-base-dir='+STATE.as_posix()+'/',*args],capture_output=True,text=True,timeout=20)
    return p.returncode,p.stdout.strip()

def authenticate(username,password,secret=SECRET):
    dictionary=Dictionary(io.StringIO('ATTRIBUTE User-Name 1 string\nATTRIBUTE User-Password 2 string\nATTRIBUTE NAS-IP-Address 4 ipaddr\nATTRIBUTE Message-Authenticator 80 octets\n'))
    # pyrad's stock transport uses select.poll, unavailable on Windows.
    # Keep its packet encoding/response verification and use a native UDP socket.
    req=AuthPacket(code=AccessRequest,secret=secret,dict=dictionary,User_Name=username,NAS_IP_Address='127.0.0.1')
    if password is not None:req['User-Password']=req.PwCrypt(password)
    req.add_message_authenticator()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1',0))
        sock.settimeout(2)
        sock.sendto(req.RequestPacket(),('127.0.0.1',PORT))
        deadline=time.monotonic()+2
        while time.monotonic()<deadline:
            sock.settimeout(max(.01,deadline-time.monotonic()))
            try:raw,address=sock.recvfrom(4096)
            except (socket.timeout,ConnectionResetError):return 'timeout'
            if address!=('127.0.0.1',PORT):continue
            reply=req.CreateReply(packet=raw)
            if req.VerifyReply(reply,raw):return reply.code
        return 'timeout'

def fresh(otp):
    delay=otp.interval-time.time()%otp.interval+.2
    print('Waiting for fresh OTP interval ('+str(round(delay,1))+' seconds)',flush=True)
    time.sleep(delay)
    return otp.now()

try:
    # The packaged 32-bit server rejects long dictionary paths. A disposable
    # drive alias shortens only this lab directory and is removed in finally.
    drive_mask=ctypes.windll.kernel32.GetLogicalDrives()
    for letter in 'ZYXWVUTSR':
        if not drive_mask & (1 << (ord(letter)-ord('A'))):
            probe=ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.QueryDosDeviceW(letter+':',probe,len(probe))==0:
                candidate=letter+':'
                mapped=subprocess.run(['subst.exe',candidate,str(LAB)],capture_output=True,text=True)
                if mapped.returncode==0:
                    DRIVE=candidate
                    break
    if DRIVE is None:raise RuntimeError('No unused temporary drive alias available')
    # Legacy exec tokenization cannot reliably launch paths containing spaces.
    # Alias existing runtime files rather than copying an incomplete PHP runtime.
    drive_mask=ctypes.windll.kernel32.GetLogicalDrives()
    for letter in 'ZYXWVUTSR':
        if not drive_mask & (1 << (ord(letter)-ord('A'))):
            probe=ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.QueryDosDeviceW(letter+':',probe,len(probe))==0:
                mapped=subprocess.run(['subst.exe',letter+':',str(WORK)],capture_output=True,text=True)
                if mapped.returncode==0:
                    RUNTIME_DRIVE=letter+':'
                    break
    if RUNTIME_DRIVE is None:raise RuntimeError('No unused runtime drive alias available')
    RUNTIME=pathlib.Path(RUNTIME_DRIVE+'/')
    SHORT=pathlib.Path(DRIVE+'/')
    SHORT_PREFIX=SHORT/'radius'
    SHORT_CONF=SHORT_PREFIX/'etc/raddb'
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.bind(('127.0.0.1',0));PORT=s.getsockname()[1]
    program=' '.join([str(RUNTIME/'php-runtime/php.exe').replace('\\','/'),'-n','-d',
        'extension_dir='+str(RUNTIME/'php-runtime/ext').replace('\\','/'),'-d','extension=mbstring','-d','extension=openssl',
        str(RUNTIME/'multiotp-engine/multiotp.php').replace('\\','/'),'-base-dir='+(SHORT/'engine-state').as_posix()+'/',
        '\\"%{User-Name}\\"','\\"%{User-Password}\\"'])
    config='''prefix = "PREFIX"
name = radiusd
confdir = "CONF"
raddbdir = ${confdir}
db_dir = ${confdir}
logdir = "LOGDIR"
run_dir = "RUNDIR"
pidfile = ${run_dir}/radiusd.pid
libdir = ${prefix}/lib
max_request_time = 15
cleanup_delay = 1
max_requests = 64
proxy_requests = no
listen {
    type = auth
    ipaddr = 127.0.0.1
    port = PORT
}
client disposable_loopback {
    ipaddr = 127.0.0.1
    netmask = 32
    secret = "SECRET"
    shortname = disposable_loopback
}
security {
    max_attributes = 64
    reject_delay = 0
    status_server = no
}
log {
    destination = files
    file = ${logdir}/radius.log
    auth = no
    auth_badpass = no
    auth_goodpass = no
    colourise = no
}
modules {
    exec multiotp {
        wait = yes
        program = "PROGRAM"
        input_pairs = request
        output_pairs = reply
        shell_escape = yes
        timeout = 10
    }
}
authorize {
    update control {
        Auth-Type := multiotp
    }
}
authenticate {
    Auth-Type multiotp {
        multiotp
    }
}
'''
    for key,value in [('PREFIX',SHORT_PREFIX.as_posix()),('CONF',SHORT_CONF.as_posix()),('LOGDIR',SHORT.as_posix()),
        ('RUNDIR',SHORT.as_posix()),('PORT',str(PORT)),('SECRET',SECRET.decode()),('PROGRAM',program)]:
        config=config.replace(key,value)
    (CONF/'radiusd.conf').write_text(config,encoding='utf-8')
    command=[str(SHORT_PREFIX/'sbin/radiusd.exe'),'-d',SHORT_CONF.as_posix(),'-i','127.0.0.1','-p',str(PORT)]
    check=subprocess.run(command+['-C'],cwd=SHORT_PREFIX/'sbin',capture_output=True,text=True,timeout=20)
    record('RADIUS configuration validation',check.returncode==0,{'exit':check.returncode})
    if check.returncode:
        print((check.stdout+check.stderr).replace(SECRET.decode(),'[REDACTED]')[-4000:],flush=True)
        if (LAB/'radius.log').exists():
            print((LAB/'radius.log').read_text().replace(SECRET.decode(),'[REDACTED]')[-2500:],flush=True)
        raise RuntimeError('RADIUS configuration validation failed')
    rc,_=cli('-fastcreatenopin',USER);record('RADIUS fake engine identity created',rc==11,{'exit':rc})
    rc,out=cli('-urllink',USER)
    otp=pyotp.parse_uri(re.search(r'otpauth://\S+',out).group())
    LOG=open(LAB/'server-process.log','w',encoding='utf-8')
    SERVER=subprocess.Popen(command+['-f','-s','-t'],cwd=SHORT_PREFIX/'sbin',stdout=LOG,stderr=LOG)
    time.sleep(1)
    for _ in range(8):
        if SERVER.poll() is not None:
            LOG.flush()
            print((LAB/'server-process.log').read_text().replace(SECRET.decode(),'[REDACTED]')[-3000:])
            raise RuntimeError('RADIUS server exited')
        if authenticate('bliss_radius_missing','000000')==AccessReject:break
    else:raise RuntimeError('RADIUS server not responding')
    snapshot=subprocess.run(['powershell.exe','-NoProfile','-Command',
        f'Get-NetUDPEndpoint -OwningProcess {SERVER.pid} | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'],
        capture_output=True,text=True,timeout=20)
    endpoints=json.loads(snapshot.stdout)
    if isinstance(endpoints,dict):endpoints=[endpoints]
    record('RADIUS binds only loopback',bool(endpoints) and all(x['LocalAddress']=='127.0.0.1' for x in endpoints),{'endpoints':endpoints})
    if not all(x['LocalAddress']=='127.0.0.1' for x in endpoints):raise RuntimeError('Unexpected listener; stopping test')
    code=otp.now()
    result=authenticate(USER,code);record('RADIUS valid OTP Access-Accept',result==AccessAccept,{'response_code':result})
    result=authenticate(USER,code);record('RADIUS OTP replay Access-Reject',result==AccessReject,{'response_code':result})
    result=authenticate(USER,'000000');record('RADIUS invalid OTP Access-Reject',result==AccessReject,{'response_code':result})
    result=authenticate(USER,None);record('RADIUS missing OTP Access-Reject',result==AccessReject,{'response_code':result})
    result=authenticate('bliss_radius_missing','000000');record('RADIUS missing identity Access-Reject',result==AccessReject,{'response_code':result})
    result=authenticate(USER,'000000',secret=secrets.token_urlsafe(32).encode());record('RADIUS wrong shared secret receives no verified response',result=='timeout',{'response_code':result})
    cli('-deactivate',USER)
    result=authenticate(USER,otp.now());record('RADIUS disabled identity Access-Reject',result==AccessReject,{'response_code':result})
    cli('-activate',USER)
    result=authenticate(USER,fresh(otp));record('RADIUS enabled identity Access-Accept',result==AccessAccept,{'response_code':result})
    cli('-lock',USER)
    result=authenticate(USER,otp.now());record('RADIUS locked identity Access-Reject',result==AccessReject,{'response_code':result})
    cli('-unlock',USER)
    result=authenticate(USER,fresh(otp));record('RADIUS unlocked identity Access-Accept',result==AccessAccept,{'response_code':result})
    cli('-deactivate',USER);cli('-remove-token',USER)
    result=authenticate(USER,otp.now());record('RADIUS revoked old OTP Access-Reject',result==AccessReject,{'response_code':result})
    cli('-delete',USER)
    result=authenticate(USER,'000000');record('RADIUS deleted identity Access-Reject',result==AccessReject,{'response_code':result})
    SERVER.terminate();SERVER.wait(timeout=10)
    result=authenticate(USER,'000000');record('RADIUS outage produces timeout',result=='timeout',{'response_code':result})
except Exception as exc:
    record('RADIUS harness completion',False,{'error_type':type(exc).__name__,'message':str(exc)})
    traceback.print_exc()
finally:
    if SERVER and SERVER.poll() is None:
        SERVER.terminate()
        try:SERVER.wait(timeout=10)
        except subprocess.TimeoutExpired:SERVER.kill();SERVER.wait()
    if LOG:LOG.close()
    alias_removed=DRIVE is None
    if DRIVE:
        alias_removed=subprocess.run(['subst.exe',DRIVE,'/D'],capture_output=True).returncode==0
    if RUNTIME_DRIVE:
        alias_removed=(subprocess.run(['subst.exe',RUNTIME_DRIVE,'/D'],capture_output=True).returncode==0) and alias_removed
    cli('-delete',USER)
    rc,out=cli('-userslist')
    remaining=len([line for line in out.splitlines() if line.strip()])
    output={'lab_directory':str(LAB),'distribution_url':'https://download.multiotp.net/oss/update/multiotp_5.10.2.2.zip',
        'distribution_sha256':'1d9af793d4264031fa7dfb4234d9bdd90ed2c5045b59c99920dc7c5c72858e2e',
        'radius_version':'FreeRADIUS 2.2.6 Windows vendor distribution','results':RESULTS,
        'server_stopped':SERVER is None or SERVER.poll() is not None,'remaining_engine_users':remaining,
        'temporary_drive_alias_removed':alias_removed,
        'scope':'Loopback UDP PAP RADIUS with real patched multiOTP. No Windows account, credential-provider, service installation, firewall, registry, or RDP change.'}
    (ROOT/'outputs/radius-lifecycle-results.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print('RADIUS RESULTS '+str(sum(x['passed'] for x in RESULTS))+'/'+str(len(RESULTS))+'; server stopped',flush=True)

sys.exit(0 if all(x["passed"] for x in RESULTS) and output["server_stopped"] and remaining==0 and alias_removed else 1)
