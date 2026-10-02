import json,urllib.request,re,os
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36","Referer":"https://m.stock.naver.com/"}
urls=["https://m.stock.naver.com/api/stocks/theme?page=1&pageSize=20",
"https://m.stock.naver.com/api/stocks/theme/1?page=1&pageSize=20",
"https://m.stock.naver.com/api/stocks/themes?page=1&pageSize=20",
"https://m.stock.naver.com/front-api/stock/domestic/theme?page=1&pageSize=20",
"https://m.stock.naver.com/api/stock/240810/integration",
"https://m.stock.naver.com/api/stock/478340/integration",
"https://m.stock.naver.com/api/stock/478340/basic",
"https://m.stock.naver.com/domestic/theme",
"https://finance.naver.com/sise/theme.naver"]
out={}
for u in urls:
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=20) as r:
            b=r.read().decode('utf-8','ignore')
        info={"len":len(b),"head":b[:700]}
        for kw in ["theme","Theme","테마"]:
            i=b.find(kw); info["at_"+kw]=b[max(0,i-200):i+400] if i>=0 else None
        out[u]=info
    except Exception as e: out[u]={"err":str(e)}
os.makedirs("data/ref",exist_ok=True)
json.dump(out,open("data/ref/probe.json","w"),ensure_ascii=False,indent=1)
