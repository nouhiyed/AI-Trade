# AI Trade

وكلاء ذكاء اصطناعي (Futures / Spot) على بيانات Binance الحقيقية. الوضع الحالي: **DEMO فقط** (أسعار حقيقية، تنفيذ تجريبي داخلي بدفتر محاسبي). **LIVE مقفل.**

## التشغيل (Termux)
```bash
pkg install python python-pandas python-numpy   # أو pip install -r requirements.txt
pip install -r requirements.txt
pkg install python-pillow                        # اختياري: صور التشارت لـ Telegram
python -m api.main                               # الخادم على 127.0.0.1:8001
```
متغيرات اختيارية: `DEMO_INITIAL_BALANCE`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
منفذ الخادم ثابت على `8001` لتوحيد اتصال التطبيق وخدمة Android.

## ما الجديد
- **Autopilot** (`core/autopilot.py`): يفحص السوق كل دقيقتين ويفتح صفقات DEMO وفق حدود المخاطر. مطفأ افتراضياً؛ يُفعَّل من شاشة «الأداء والآلي».
- **سجل الصفقات** (`core/journal.py`) + **الأداء** (`/performance`).
- **التعلّم المنضبط** (`core/learning.py`): لا تغيير قبل 30 صفقة لكل نمط؛ النمط ذو التوقع السلبي يُوقَف تلقائياً ويمكن إعادة تفعيله يدوياً.
- **سياق داعم** (`core/market_context.py`): funding, long/short, تدفق الحيتان, أخبار RSS. يؤكد أو يعترض فقط، والقرار فني.
- **تعويض الانقطاع**: عند عودة الشبكة تُعاد قراءة شموع الدقيقة لمعرفة هل لُمس الوقف أو الهدف أثناء الغياب.
- **Telegram**: رسالة + صورة تشارت (دخول/وقف/أهداف) عند فتح الصفقة وعند إغلاقها.
- **تشارت احترافي** في التطبيق (Lightweight Charts): EMA, Bollinger, VWAP, RSI, MACD, حجم، وخطوط الصفقات.

## Spot (DEMO)
- شراء فقط (Long) بسعر الـ ask وبيع بسعر الـ bid، مع وقف/هدف من خطة الصفقة وتعويض الانقطاع بالشموع.
- يمر عبر إدارة المخاطر والسجل والتعلّم والإشعارات.

## Endpoints جديدة
`GET /performance /journal /learning /autopilot` · `POST /autopilot /autopilot/run /learning/enable /scan/spot` · `POST /demo/open` يقبل `"domain": "futures|spot"`

## الاختبارات
```bash
python -m unittest discover -s tests -t . -v
```

## تنبيهات
نتائج الديمو أفضل غالباً من الحقيقة. لا تفعّل LIVE قبل مئة صفقة ديمو على الأقل ومراجعة الأداء.
