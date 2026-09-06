"""
Patches the installed Pycord voice gateway to include max_dave_protocol_version=1
in the IDENTIFY payload, which is required by Discord's mandatory DAVE E2EE
protocol (enforced globally from March 2026).
"""
import os

gateway_path = r'C:\Users\troke\tony_venv\Lib\site-packages\discord\gateway.py'
with open(gateway_path, 'r', encoding='utf-8') as f:
    content = f.read()

# The old voice identify payload (inside DiscordVoiceWebSocket)
OLD = (
    '                "server_id": str(state.server_id),\n'
    '                "user_id": str(state.user.id),\n'
    '                "session_id": state.session_id,\n'
    '                "token": state.token,\n'
    '            },\n'
    '        }\n'
    '        await self.send_as_json(payload)'
)

NEW = (
    '                "server_id": str(state.server_id),\n'
    '                "user_id": str(state.user.id),\n'
    '                "session_id": state.session_id,\n'
    '                "token": state.token,\n'
    '                "max_dave_protocol_version": 1,\n'
    '            },\n'
    '        }\n'
    '        await self.send_as_json(payload)'
)

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    with open(gateway_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[OK] Patched DiscordVoiceWebSocket.identify() with max_dave_protocol_version=1")
elif "max_dave_protocol_version" in content:
    print("[ALREADY PATCHED] max_dave_protocol_version already present in gateway.py")
else:
    print("[FAIL] Could not find the target block. Showing last identify() block:")
    idx = content.rfind("async def identify")
    print(content[idx:idx+800])
