s=open('app.js',encoding='utf-8').read()
key="msg.type === 'matched'"
i=s.find(key)
print(repr(s[i-80:i+160]))
