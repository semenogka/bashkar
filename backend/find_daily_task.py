s=open('app/api/v1.py',encoding='utf-8').read()
i=s.find('async def daily_task(')
print(s[i:i+1800])
