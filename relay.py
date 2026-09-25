"""
RemotePC Relay Sunucusu
Agent ve Viewer arasındaki trafiği yönlendirir.
Render.com / Railway.app gibi ücretsiz servislerde çalışır.
"""
import os
from flask import Flask, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(
    app, cors_allowed_origins='*',
    async_mode='eventlet',
    max_http_buffer_size=20 * 1024 * 1024  # 20 MB (dosya transferi için)
)

agents  = {}   # {device_id: sid}
viewers = {}   # {viewer_sid: device_id} — doğrulanmış
pending = {}   # {viewer_sid: device_id} — doğrulama bekliyor

# ─── Yardımcılar ───────────────────────────────────────────
def sid_to_device(sid):
    return next((did for did, s in agents.items() if s == sid), None)

def viewers_of(did):
    return [s for s, d in viewers.items() if d == did]

# ─── Genel ─────────────────────────────────────────────────
@app.route('/health')
def health():
    return f'OK — {len(agents)} agent, {len(viewers)} viewer'

@socketio.on('disconnect')
def on_disc():
    sid = request.sid
    # Agent çevrimdışı
    for did in list(agents):
        if agents[did] == sid:
            del agents[did]
            print(f'[-] Agent offline: {did}')
            # Bağlı viewer'lara haber ver
            for vsid in viewers_of(did):
                socketio.emit('agent_offline', {}, to=vsid)
    # Viewer çevrimdışı
    did = viewers.pop(sid, None) or pending.pop(sid, None)
    if did and did in agents:
        socketio.emit('viewer_left', {'vsid': sid}, to=agents[did])

# ─── Agent Olayları ────────────────────────────────────────
@socketio.on('agent_reg')
def agent_reg(d):
    did = d.get('id', '').strip()
    if did:
        agents[did] = request.sid
        print(f'[+] Agent online: {did}')
        emit('registered', {'ok': True})

@socketio.on('agent_auth_resp')
def agent_auth_resp(d):
    vsid = d.get('vsid')
    ok   = d.get('ok', False)
    if ok and vsid in pending:
        viewers[vsid] = pending.pop(vsid)
    else:
        pending.pop(vsid, None)
    socketio.emit('auth_result', {
        'ok':   ok,
        'msg':  d.get('msg', ''),
        'home': d.get('home', '')
    }, to=vsid)

@socketio.on('frame')
def fwd_frame(d):
    did = sid_to_device(request.sid)
    if did:
        for vsid in viewers_of(did):
            socketio.emit('frame', d, to=vsid)

@socketio.on('a2v')
def agent_to_viewer(d):
    did = sid_to_device(request.sid)
    if did:
        for vsid in viewers_of(did):
            socketio.emit('a2v', d, to=vsid)

# ─── Viewer Olayları ───────────────────────────────────────
@socketio.on('viewer_join')
def viewer_join(d):
    did = d.get('id', '').strip()
    pw  = d.get('pw', '')
    if did not in agents:
        emit('auth_result', {'ok': False, 'msg': f'"{did}" cihazı çevrimdışı veya bulunamadı.'})
        return
    pending[request.sid] = did
    socketio.emit('viewer_req', {'vsid': request.sid, 'pw': pw}, to=agents[did])

@socketio.on('v2a')
def viewer_to_agent(d):
    did = viewers.get(request.sid)
    if did and did in agents:
        socketio.emit('v2a', d, to=agents[did])

# ─── Başlat ────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f'Relay başlatıldı: port {port}')
    socketio.run(app, host='0.0.0.0', port=port)
