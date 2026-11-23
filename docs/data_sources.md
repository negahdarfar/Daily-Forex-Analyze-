# رجیستری و محدودیت منابع

- `config/analysis_sources.json`: نامزدهای پژوهشی و وضعیت اتصال منابع.
- `config/news_sources.json`: RSSهای فعال‌شده با کنترل رجیستری.
- `src/data/official_data.py`: داده‌های رسمی ECB، World Bank، BLS، CFTC و FRED.
- `src/data/market_data.py`: قیمت Yahoo Finance و Binance فقط برای ابزار با quote currency منطبق.

## قواعد هویت ابزار
- نماد `BTCUSD` فقط داده مظنه USD می‌پذیرد؛ داده `BTCUSDT` بدون تبدیل و منبع نرخ تبدیل، جایگزین BTCUSD نمی‌شود.
- `USD_IRR_FREE` و `USD_IRT_FREE` ابزارهای جدا هستند و هیچ‌کدام تا اتصال منبع timestampدار فعال نیستند.
- `GC=F` و `SI=F` قراردادهای آتی پیوسته/نماینده‌اند، نه قیمت نقدی XAUUSD/XAGUSD.
- `CL=F` و `BZ=F` نماینده قراردادهای آتی پیوسته WTI و Brent هستند؛ مشخصات قرارداد و قیمت اجرایی باید از venue تأیید شود.
- ثبت منبع در رجیستری به معنی دسترسی API، مجوز scrape یا صحت محتوای آن نیست.
- خطا، paywall، CAPTCHA یا محدودیت دسترسی دور زده نمی‌شود.
