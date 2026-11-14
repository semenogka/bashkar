s=open('app.js',encoding='utf-8').read()
key="pvpPlayBtn.addEventListener('click'"
i=s.find(key)
print(repr(s[i:i+260]))
