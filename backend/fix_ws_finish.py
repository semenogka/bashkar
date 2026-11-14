s=open('app/api/v1.py',encoding='utf-8').read()
old = '''            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
    for u in users:
        _PVP_WS.pop(u, None)
        _PVP_WS_USER_MATCH.pop(u, None)'''
new = '''            except Exception:
                pass
        try:
            await asyncio.sleep(0.25)
        except Exception:
            pass
        try:
            await ws.close()
        except Exception:
            pass
    for u in users:
        _PVP_WS.pop(u, None)
        _PVP_WS_USER_MATCH.pop(u, None)'''
assert old in s
s=s.replace(old,new,1)
open('app/api/v1.py','w',encoding='utf-8').write(s)
print('done')
