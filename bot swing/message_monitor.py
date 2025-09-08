import asyncio
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
from telethon.tl.types import User, Channel
import pytz
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import *
import re

# تحميل المتغيرات البيئية
load_dotenv('config.env')

class TelegramMonitor:
    def __init__(self):
        self.api_id = os.getenv('TELEGRAM_API_ID')
        self.api_hash = os.getenv('TELEGRAM_API_HASH')
        self.phone = os.getenv('TELEGRAM_PHONE')
        # إنشاء اسم فريد للجلسة
        session_name = f"my_session_{self.api_id}"
        self.client = TelegramClient(session_name, self.api_id, self.api_hash, device_model="MacBook Pro", system_version="macOS")
        self.monitored_groups = []
        self.source_channel = os.getenv('TELEGRAM_SOURCE')  # @username أو ID رقمي أو رابط
        
        # إعادة توجيه التوصيات (بدون أسئلة)
        self.forwarding_enabled = True
        self.forward_phone = "+213542027172"
        self.forward_recipient = None  # كيان Telethon للمرسل إليه
        self.forward_test_on_start = os.getenv('FORWARD_TEST_ON_START', 'false').lower() == 'true'
        
        # إضافة Binance Trader
        self.binance_trader = BinanceTrader()
        
    async def start(self):
        print("🚀 بدء تشغيل بوت مراقبة Telegram...")
        
        # محاولة الاتصال مع الجلسة المحفوظة
        try:
            await self.client.connect()
            if await self.client.is_user_authorized():
                print("✅ تم الاتصال بـ Telegram بنجاح! (جلسة محفوظة)")
            else:
                print("🔐 يلزم إدخال رمز التحقق...")
                await self.client.start(phone=self.phone)
                print("✅ تم الاتصال بـ Telegram بنجاح!")
        except Exception as e:
            print(f"❌ خطأ في الاتصال: {e}")
            await self.client.start(phone=self.phone)
            print("✅ تم الاتصال بـ Telegram بنجاح!")
        
        # تهيئة مستلم إعادة التوجيه الثابت
        await self._init_fixed_forward_recipient()

        # تهيئة القناة المصدر الثابتة
        await self._init_fixed_source_channel()
        
        # إرسال آخر توصية موجودة في القناة (مرة واحدة عند البدء)
        await self._forward_last_recommendation_once()

        # تم إلغاء إرسال الاختبار عند البدء بناءً على طلب المستخدم
        
        # بدء المراقبة
        await self.start_monitoring()
        
    async def _init_fixed_source_channel(self):
        """تهيئة القناة المصدر:
        - إذا تم تعيين TELEGRAM_SOURCE: نستخدمه مباشرة (@username أو رابط t.me أو ID)
        - إذا لم يُعيّن: نلتقط أول قناة/مجموعة من قائمة الحوارات تلقائياً
        """
        try:
            entity = None
            if self.source_channel:
                # استخدام القيمة المحددة من البيئة
                entity = await self.client.get_entity(self.source_channel)
            else:
                # التقاط أول قناة/مجموعة متاحة
                async for dialog in self.client.iter_dialogs():
                    if dialog.is_channel or dialog.is_group:
                        entity = dialog.entity
                        break
                if entity is None:
                    raise RuntimeError("لم يتم العثور على أي قناة أو مجموعة في هذا الحساب")

            self.monitored_groups = [entity]
            title = getattr(entity, 'title', None) or getattr(entity, 'username', None) or str(getattr(entity, 'id', 'channel'))
            if self.source_channel:
                print(f"✅ سيتم مراقبة قناة واحدة فقط: {title}")
            else:
                print(f"✅ TELEGRAM_SOURCE غير محدد — سيتم مراقبة أول قناة: {title}")
        except Exception as e:
            print(f"❌ تعذر تهيئة القناة المصدر: {e}")
            raise
        
    async def _forward_last_recommendation_once(self):
        """يرسل آخر رسالة موجودة في القناة لمرة واحدة عند البدء (أيّاً كان محتواها)."""
        if not (self.forwarding_enabled and self.forward_recipient is not None):
            return
        try:
            src = self.monitored_groups[0]
            print("🔎 إرسال آخر رسالة في القناة مرة واحدة عند البدء...")
            async for msg in self.client.iter_messages(src, limit=1):
                try:
                    await self.client.forward_messages(self.forward_recipient, msg)
                    print("➡️ تم إعادة توجيه آخر رسالة موجودة في القناة")
                except Exception as fe:
                    print(f"❌ فشل إعادة توجيه آخر رسالة: {fe}")
                break
        except Exception as e:
            print(f"❌ خطأ أثناء محاولة إرسال آخر توصية: {e}")
        
    async def setup_trading(self):
        """تعطيل أي تفاعل للتداول في هذا النمط الثابت"""
        self.binance_trader.trading_enabled = False
        
    async def market_analysis_menu(self):
        """تعطيل القائمة التفاعلية في هذا النمط"""
        return
        
    async def start_monitoring(self):
        print("\n🔍 بدء مراقبة الرسائل الجديدة...")
        print("=" * 50)
        
        # إعداد معالج الرسائل الجديدة
        @self.client.on(events.NewMessage(chats=self.monitored_groups))
        async def handle_new_message(event):
            message = event.message
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            sender_name = self.get_sender_name(sender)
            timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")
            
            print(f"\n📨 رسالة جديدة في {chat.title}")
            print(f"👤 من: {sender_name}")
            print(f"⏰ الوقت: {timestamp}")
            print(f"📝 المحتوى: {message.text}")
            print("-" * 50)
            
            # تحليل التوصية المتقدمة + الإشارة البسيطة
            if message.text:
                recommendation = self.binance_trader.parse_recommendation(message.text)
                if recommendation:
                    print("🎯 توصية مكتشفة:")
                    print(f"   الرمز: {recommendation['symbol']}")
                    print(f"   نطاق الشراء: {recommendation['buy_range']['min']:,.4f} - {recommendation['buy_range']['max']:,.4f}")
                    print(f"   هدف الربح (2%): {recommendation['take_profit']:,.4f}")
                    print(f"   وقف الخسارة (إغلاق 4س تحت): {recommendation['stop_loss']:,.4f}")

                    # إعادة توجيه التوصيات فقط
                    if self.forwarding_enabled and self.forward_recipient is not None:
                        try:
                            await self.client.forward_messages(self.forward_recipient, message)
                            print("➡️ تم إعادة توجيه التوصية إلى المستلم المحدد")
                        except Exception as e:
                            print(f"❌ فشل إعادة توجيه التوصية: {e}")
                else:
                    # fallback على النموذج القديم البسيط إن لزم
                    signal = self.binance_trader.parse_trading_signal(message.text)
                    if signal:
                        print(f"🎯 إشارة تداول مكتشفة!")
                        print(f"   العملة: {signal['symbol']}")
                        print(f"   الإجراء: {signal['action']}")
                        print(f"   السعر: {signal['price']}")
                        
                        # تنفيذ الصفقة
                        if self.binance_trader.trading_enabled:
                            success = self.binance_trader.execute_trade(signal)
                            if success:
                                print("✅ تم تنفيذ الصفقة بنجاح!")
                            else:
                                print("❌ فشل في تنفيذ الصفقة")
                        else:
                            print("⚠️ التداول التلقائي معطل - الإشارة محفوظة فقط")
                
                # تحليل السوق عند ذكر عملة معينة
                if "تحليل" in message.text.lower() or "سعر" in message.text.lower():
                    # البحث عن رمز العملة في الرسالة
                    import re
                    symbol_match = re.search(r'([A-Z]{3,10}USDT)', message.text.upper())
                    if symbol_match:
                        symbol = symbol_match.group(1)
                        print(f"📊 تحليل تلقائي لـ {symbol}...")
                        self.binance_trader.analyze_market(symbol)
            
        # الاستمرار في المراقبة
        await self.client.run_until_disconnected()

    async def _init_fixed_forward_recipient(self):
        """تهيئة كيان المستلم الثابت من رقم الهاتف المحدد مسبقاً."""
        if not self.forwarding_enabled:
            return
        try:
            # محاولة جلب الكيان مباشرة بالهاتف
            entity = None
            try:
                entity = await self.client.get_entity(self.forward_phone)
            except Exception:
                entity = None

            if entity is None:
                # استيراد جهة الاتصال إن لم تكن موجودة في الدفتر
                contact = InputPhoneContact(client_id=0, phone=self.forward_phone, first_name="Forward", last_name="Target")
                result = await self.client(ImportContactsRequest([contact]))
                if result.users:
                    entity = result.users[0]

            if entity is not None:
                self.forward_recipient = entity
                name = getattr(entity, 'title', None) or getattr(entity, 'username', None) or getattr(entity, 'first_name', 'مستلم')
                print(f"✅ سيتم إعادة توجيه التوصيات إلى: {name}")
            else:
                print("⚠️ لم يتم العثور على المستلم عبر الهاتف. سيتم تعطيل إعادة التوجيه.")
                self.forwarding_enabled = False
        except Exception as e:
            print(f"❌ فشل تهيئة مستلم إعادة التوجيه: {e}")
            self.forwarding_enabled = False
            self.forward_recipient = None
        
    async def show_todays_messages(self):
        print("\n📅 رسائل اليوم:")
        print("=" * 50)
        
        # تحديد بداية اليوم (UTC)
        utc_now = datetime.now(pytz.UTC)
        start_of_day = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        for channel_id in self.monitored_groups:
            try:
                entity = await self.client.get_entity(channel_id)
                print(f"\n📺 رسائل قناة: {entity.title}")
                
                # جلب جميع الرسائل من اليوم
                messages = []
                async for message in self.client.iter_messages(entity, limit=1000):
                    # تحويل تاريخ الرسالة إلى UTC إذا لم يكن كذلك
                    message_date = message.date
                    if message_date.tzinfo is None:
                        message_date = pytz.UTC.localize(message_date)
                    
                    # فلترة رسائل اليوم فقط
                    if message_date >= start_of_day and message.text:
                        messages.append(message)
                
                # ترتيب الرسائل من الأقدم إلى الأحدث
                messages.sort(key=lambda x: x.date)
                
                if messages:
                    print(f"✅ تم العثور على {len(messages)} رسالة من اليوم")
                    print("=" * 50)
                    
                    for message in messages:
                        sender = await message.get_sender()
                        sender_name = self.get_sender_name(sender)
                        timestamp = message.date.strftime("%H:%M:%S")
                        
                        print(f"👤 {sender_name} | ⏰ {timestamp}")
                        print(f"📝 {message.text}")
                        print("-" * 30)
                else:
                    print("⚠️ لا توجد رسائل من اليوم")
                    
            except Exception as e:
                print(f"❌ خطأ في جلب رسائل القناة {channel_id}: {e}")
                
    def get_sender_name(self, sender):
        if isinstance(sender, User):
            if sender.first_name and sender.last_name:
                return f"{sender.first_name} {sender.last_name}"
            elif sender.first_name:
                return sender.first_name
            elif sender.username:
                return f"@{sender.username}"
            else:
                return "مستخدم مجهول"
        elif isinstance(sender, Channel):
            return sender.title
        else:
            return "مصدر مجهول"

class BinanceTrader:
    def __init__(self):
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret_key = os.getenv('BINANCE_SECRET_KEY')
        self.testnet = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'
        
        # التحقق من وجود بيانات API
        if not self.api_key or not self.secret_key:
            print("⚠️ بيانات Binance API غير موجودة في config.env")
            print("   أضف BINANCE_API_KEY و BINANCE_SECRET_KEY")
            self.client = None
            return
        
        try:
            if self.testnet:
                self.client = Client(self.api_key, self.secret_key, testnet=True)
                print("🧪 تم الاتصال بـ Binance Testnet")
            else:
                self.client = Client(self.api_key, self.secret_key)
                print("💰 تم الاتصال بـ Binance Live")
        except Exception as e:
            print(f"❌ خطأ في الاتصال بـ Binance: {e}")
            self.client = None
            
        self.trading_enabled = False
        self.max_position_size = 0.1  # 10% من الرصيد
        
    def parse_trading_signal(self, message_text):
        """تحليل رسالة التداول واستخراج الإشارة"""
        patterns = {
            'buy': [
                r'شراء\s+([A-Z]+/[A-Z]+)\s+عند\s+([\d.]+)',
                r'buy\s+([A-Z]+/[A-Z]+)\s+at\s+([\d.]+)',
                r'long\s+([A-Z]+/[A-Z]+)\s+([\d.]+)',
                r'([A-Z]+/[A-Z]+)\s+شراء\s+([\d.]+)',
            ],
            'sell': [
                r'بيع\s+([A-Z]+/[A-Z]+)\s+عند\s+([\d.]+)',
                r'sell\s+([A-Z]+/[A-Z]+)\s+at\s+([\d.]+)',
                r'short\s+([A-Z]+/[A-Z]+)\s+([\d.]+)',
                r'([A-Z]+/[A-Z]+)\s+بيع\s+([\d.]+)',
            ]
        }
        
        message_lower = message_text.lower()
        
        for action, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, message_text, re.IGNORECASE)
                if match:
                    symbol = match.group(1).replace('/', '')
                    price = float(match.group(2))
                    return {
                        'action': action,
                        'symbol': symbol,
                        'price': price,
                        'message': message_text
                    }
        return None

    # ===================== محلل متقدم لتوصيات القناة =====================
    def parse_recommendation(self, message_text):
        """تحليل متقدم لتوصية القناة لاستخراج:
        - الرمز (ديناميكياً من $btc أو btcusdt)
        - نطاق الشراء (min,max) من buy/شراء/entry/دخول
        - وقف الخسارة كإغلاق شمعة 4 ساعات تحت سعر معين
        - هدف ربح ثابت 2% من أدنى سعر دخول
        يعيد None إن لم تُستخرج العناصر الأساسية.
        """
        if not message_text:
            return None
        text = message_text.strip()

        symbol = self._extract_symbol(text)
        buy_range = self._extract_buy_range(text)
        stop_loss = self._extract_stop_loss(text)

        if not symbol or not buy_range or stop_loss is None:
            return None

        entry_min = buy_range['min']
        take_profit = entry_min * 1.02  # +2%

        return {
            'symbol': symbol,
            'buy_range': buy_range,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'raw': message_text,
        }

    def _extract_symbol(self, text):
        """يكتشف الرمز من:
        - $btc أو $eth ... إلخ → يحول إلى BTCUSDT
        - btcusdt/ethusdt مذكورة مباشرة
        - BTC/USDT أو ETH/USDT → يحول إلى BTCUSDT
        - CYBER|USDT| (التنسيق الجديد)
        """
        # $xxx
        m = re.search(r"\$([a-zA-Z]{2,10})", text)
        if m:
            code = m.group(1).upper()
            return f"{code}USDT" if not code.endswith("USDT") else code

        # SYMBOL|USDT| (التنسيق الجديد)
        m = re.search(r"([A-Z]{2,10})\|USDT\|", text)
        if m:
            return f"{m.group(1).upper()}USDT"

        # SYMBOLUSDT
        m = re.search(r"\b([A-Z]{2,10}USDT)\b", text)
        if m:
            return m.group(1).upper()

        # SYMBOL/USDT
        m = re.search(r"\b([A-Z]{2,10})\s*/\s*USDT\b", text)
        if m:
            return f"{m.group(1).upper()}USDT"

        return None

    def _extract_buy_range(self, text):
        """يستخرج نطاق الشراء من أنماط مختلفة عربية/إنجليزية.
        يدعم أرقام مع فواصل أو كسور عشرية.
        أمثلة: buy 109500,110000 | شراء 3000,3100 | entry 95,98 | دخول 0.45,0.47
        BUY : 1.730 - 1.745 (التنسيق الجديد)
        """
        patterns = [
            r"\b(?:buy|شراء|entry|دخول)\s+([\d.,]+)\s*,\s*([\d.,]+)",
            r"BUY\s*:\s*([\d.,]+)\s*-\s*([\d.,]+)",  # التنسيق الجديد
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                p1 = float(m.group(1).replace(',', ''))
                p2 = float(m.group(2).replace(',', ''))
                lo, hi = (p1, p2) if p1 <= p2 else (p2, p1)
                return {'min': lo, 'max': hi}
        return None

    def _extract_stop_loss(self, text):
        """يستخرج سعر وقف الخسارة على شكل: إغلاق شمعة 4 ساعات تحت X.
        يدعم عدة صيغ عربية/إنجليزية مبسطة.
        STOP 1.68 (التنسيق الجديد)
        """
        patterns = [
            r"stop\s+los?e?\s+.*?4\s*ساعات\s*تحت\s*([\d.,]+)",
            r"وقف\s*خسارة\s+.*?4\s*ساعات\s*تحت\s*([\d.,]+)",
            r"خسارة\s+.*?4\s*ساعات\s*تحت\s*([\d.,]+)",
            r"STOP\s+([\d.,]+)",  # التنسيق الجديد
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return float(m.group(1).replace(',', ''))
        return None

    def test_recommendation_parser(self):
        """اختبار سريع للمحلل مع التوصية الحقيقية"""
        test_message = """❇️CYBER|USDT|


🔱 BUY  : 1.730 -  1.745

T 🎯 :

1️⃣: 1.775
2️⃣: 1.810
3️⃣: 1.900
4️⃣: 2.100
5️⃣: 2.350


🔴STOP  1.68  ا"""
        
        print("🧪 اختبار المحلل المتقدم:")
        print("=" * 50)
        print("📝 الرسالة:")
        print(test_message)
        print("=" * 50)
        
        result = self.parse_recommendation(test_message)
        if result:
            print("✅ تم استخراج التوصية بنجاح!")
            print(f"🎯 الرمز: {result['symbol']}")
            print(f"💰 نطاق الشراء: {result['buy_range']['min']:,.4f} - {result['buy_range']['max']:,.4f}")
            print(f"📈 هدف الربح (2%): {result['take_profit']:,.4f}")
            print(f"🛑 وقف الخسارة: {result['stop_loss']:,.4f}")
        else:
            print("❌ فشل في استخراج التوصية")
        
        print("=" * 50)
        return result
        
    def execute_trade(self, signal):
        """تنفيذ الصفقة"""
        if not self.client:
            print("❌ Binance غير متصل")
            return False
            
        if not self.trading_enabled:
            print("⚠️ التداول التلقائي معطل")
            return False
            
        try:
            symbol = signal['symbol']
            action = signal['action']
            price = signal['price']
            
            # الحصول على معلومات الحساب
            account = self.client.get_account()
            usdt_balance = float([asset for asset in account['balances'] if asset['asset'] == 'USDT'][0]['free'])
            
            # حساب حجم الصفقة
            position_size = usdt_balance * self.max_position_size
            
            if action == 'buy':
                # شراء
                quantity = position_size / price
                order = self.client.create_order(
                    symbol=symbol,
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
                print(f"✅ تم الشراء: {symbol} - الكمية: {quantity} - السعر: {price}")
                
            elif action == 'sell':
                # بيع
                # أولاً نتحقق من الرصيد المتوفر
                asset_balance = float([asset for asset in account['balances'] if asset['asset'] == symbol.replace('USDT', '')][0]['free'])
                
                if asset_balance > 0:
                    order = self.client.create_order(
                        symbol=symbol,
                        side=SIDE_SELL,
                        type=ORDER_TYPE_MARKET,
                        quantity=asset_balance
                    )
                    print(f"✅ تم البيع: {symbol} - الكمية: {asset_balance}")
                else:
                    print(f"❌ لا يوجد رصيد كافي لبيع {symbol}")
                    
            return True
            
        except Exception as e:
            print(f"❌ خطأ في تنفيذ الصفقة: {e}")
            return False
            
    def get_account_info(self):
        """الحصول على معلومات الحساب"""
        if not self.client:
            print("❌ Binance غير متصل")
            return []
            
        try:
            account = self.client.get_account()
            balances = []
            
            for asset in account['balances']:
                if float(asset['free']) > 0:
                    balances.append({
                        'asset': asset['asset'],
                        'free': float(asset['free']),
                        'locked': float(asset['locked'])
                    })
                    
            return balances
        except Exception as e:
            print(f"❌ خطأ في جلب معلومات الحساب: {e}")
            return []
    
    def get_current_price(self, symbol):
        """الحصول على السعر الحالي"""
        if not self.client:
            print("❌ Binance غير متصل")
            return None
            
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"❌ خطأ في جلب السعر الحالي: {e}")
            return None
    
    def show_detailed_price(self, symbol):
        """عرض السعر المفصل"""
        if not self.client:
            print("❌ Binance غير متصل")
            return
            
        print(f"\n💰 السعر المفصل: {symbol}")
        print("=" * 60)
        
        detailed_price = self.get_detailed_price(symbol)
        if detailed_price:
            # السعر الحالي
            current_price = detailed_price['current_price']
            price_change = detailed_price['price_change_24h']
            price_change_percent = detailed_price['price_change_percent_24h']
            
            print(f"🎯 السعر الحالي:     {current_price:>15,.4f} USDT")
            
            # التغير في 24 ساعة
            change_symbol = "📈" if price_change >= 0 else "📉"
            print(f"{change_symbol} التغير (24س):   {price_change:>+15,.2f} USDT ({price_change_percent:>+6.2f}%)")
            
            # أعلى وأقل سعر في 24 ساعة
            print(f"📈 أعلى (24س):       {detailed_price['high_24h']:>15,.2f} USDT")
            print(f"📉 أقل (24س):        {detailed_price['low_24h']:>15,.2f} USDT")
            print(f"📊 الفتح (24س):       {detailed_price['open_price_24h']:>15,.2f} USDT")
            
            # الحجم
            print(f"📊 الحجم (24س):      {detailed_price['volume_24h']:>15,.2f}")
            print(f"💰 قيمة التداول:     {detailed_price['quote_volume_24h']:>15,.2f} USDT")
            
            # آخر صفقة
            print(f"🔄 آخر صفقة:         {detailed_price['last_trade_price']:>15,.2f} USDT")
            
            # عمق السوق
            print(f"📈 أعلى عرض شراء:    {detailed_price['bid_price']:>15,.2f} USDT")
            print(f"📉 أقل عرض بيع:      {detailed_price['ask_price']:>15,.2f} USDT")
            print(f"📏 الفرق (Spread):    {detailed_price['spread']:>15,.2f} USDT")
            
            # حساب نسبة الفرق
            if current_price > 0:
                spread_percent = (detailed_price['spread'] / current_price) * 100
                print(f"📊 نسبة الفرق:       {spread_percent:>15,.4f}%")
            
            # تحليل السعر
            print(f"\n📊 تحليل السعر:")
            print("-" * 30)
            
            # اتجاه السعر
            if price_change > 0:
                print(f"📈 الاتجاه: صاعد (Bullish)")
            elif price_change < 0:
                print(f"📉 الاتجاه: هابط (Bearish)")
            else:
                print(f"⚪ الاتجاه: مستقر")
            
            # قوة التداول
            if detailed_price['volume_24h'] > 1000000:  # أكثر من مليون
                print(f"🔥 حجم التداول: عالي")
            elif detailed_price['volume_24h'] > 100000:  # أكثر من 100 ألف
                print(f"📊 حجم التداول: متوسط")
            else:
                print(f"📉 حجم التداول: منخفض")
            
            # تقييم السيولة
            if detailed_price['spread'] < current_price * 0.001:  # أقل من 0.1%
                print(f"💧 السيولة: ممتازة")
            elif detailed_price['spread'] < current_price * 0.005:  # أقل من 0.5%
                print(f"📊 السيولة: جيدة")
            else:
                print(f"⚠️ السيولة: منخفضة")
                
        else:
            print("❌ لا يمكن جلب بيانات السعر المفصل")
        
        print("=" * 60)
    
    def show_simple_analysis(self, symbol):
        """عرض السعر الحالي + شمعات 4 ساعات"""
        if not self.client:
            print("❌ Binance غير متصل")
            return
            
        print(f"\n📊 {symbol}")
        print("=" * 50)
        
        # السعر الحالي
        current_price = self.get_current_price(symbol)
        if current_price:
            print(f"💰 السعر الحالي: {current_price:,.4f} USDT")
        
        # شمعات 4 ساعات
        candles = self.get_4h_candles(symbol, 4)
        if candles:
            print(f"\n📈 شمعات 4 ساعات:")
            print("-" * 50)
            
            for i, candle in enumerate(candles, 1):
                # تحويل الوقت إلى تاريخ مقروء
                from datetime import datetime
                candle_time = datetime.fromtimestamp(candle['open_time'] / 1000)
                time_str = candle_time.strftime("%Y-%m-%d %H:%M")
                
                print(f"🕯️ شمعة {i} - {time_str}")
                print(f"   الفتح:   {candle['open']:,.4f}")
                print(f"   الأعلى:  {candle['high']:,.4f}")
                print(f"   الأقل:   {candle['low']:,.4f}")
                print(f"   الإغلاق: {candle['close']:,.4f}")
                print(f"   الحجم:   {candle['volume']:,.2f}")
                
                # حساب التغير
                change = candle['close'] - candle['open']
                change_percent = (change / candle['open']) * 100
                change_symbol = "📈" if change >= 0 else "📉"
                
                print(f"   التغير: {change_symbol} {change:+,.4f} ({change_percent:+.2f}%)")
                print("-" * 30)
        else:
            print("❌ لا يمكن جلب بيانات الشمعات")
        
        print("=" * 50)
    
    def get_detailed_price(self, symbol):
        """الحصول على السعر المفصل مع 24 ساعة"""
        if not self.client:
            print("❌ Binance غير متصل")
            return None
            
        try:
            # الحصول على معلومات السعر المفصلة
            ticker_24h = self.client.get_ticker(symbol=symbol)
            
            # الحصول على آخر صفقة
            recent_trades = self.client.get_recent_trades(symbol=symbol, limit=1)
            
            # الحصول على عمق السوق
            order_book = self.client.get_order_book(symbol=symbol, limit=5)
            
            return {
                'symbol': symbol,
                'current_price': float(ticker_24h['lastPrice']),
                'price_change_24h': float(ticker_24h['priceChange']),
                'price_change_percent_24h': float(ticker_24h['priceChangePercent']),
                'high_24h': float(ticker_24h['highPrice']),
                'low_24h': float(ticker_24h['lowPrice']),
                'volume_24h': float(ticker_24h['volume']),
                'quote_volume_24h': float(ticker_24h['quoteVolume']),
                'open_price_24h': float(ticker_24h['openPrice']),
                'last_trade_price': float(recent_trades[0]['price']) if recent_trades else float(ticker_24h['lastPrice']),
                'bid_price': float(order_book['bids'][0][0]) if order_book['bids'] else float(ticker_24h['lastPrice']),
                'ask_price': float(order_book['asks'][0][0]) if order_book['asks'] else float(ticker_24h['lastPrice']),
                'spread': float(order_book['asks'][0][0]) - float(order_book['bids'][0][0]) if order_book['asks'] and order_book['bids'] else 0
            }
        except Exception as e:
            print(f"❌ خطأ في جلب السعر المفصل: {e}")
            return None
    
    def get_4h_candles(self, symbol, limit=4):
        """الحصول على شمعات 4 ساعات"""
        if not self.client:
            print("❌ Binance غير متصل")
            return []
            
        try:
            klines = self.client.get_klines(
                symbol=symbol,
                interval=KLINE_INTERVAL_4HOUR,
                limit=limit
            )
            
            candles = []
            for kline in klines:
                candles.append({
                    'open_time': kline[0],
                    'open': float(kline[1]),
                    'high': float(kline[2]),
                    'low': float(kline[3]),
                    'close': float(kline[4]),
                    'volume': float(kline[5])
                })
            
            return candles
        except Exception as e:
            print(f"❌ خطأ في جلب الشمعات: {e}")
            return []
    
    def calculate_rsi(self, prices, period=14):
        """حساب مؤشر القوة النسبية RSI"""
        if len(prices) < period + 1:
            return 50.0  # قيمة افتراضية
            
        deltas = []
        for i in range(1, len(prices)):
            deltas.append(prices[i] - prices[i-1])
        
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """حساب مؤشر MACD"""
        if len(prices) < slow:
            return {'macd': 0, 'signal': 0, 'histogram': 0}
        
        # حساب المتوسطات المتحركة الأسية
        def ema(data, period):
            alpha = 2 / (period + 1)
            ema_values = [data[0]]
            for i in range(1, len(data)):
                ema_values.append(alpha * data[i] + (1 - alpha) * ema_values[-1])
            return ema_values
        
        ema_fast = ema(prices, fast)
        ema_slow = ema(prices, slow)
        
        # حساب MACD line
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(ema_fast))]
        
        # حساب Signal line
        signal_line = ema(macd_line, signal)
        
        # حساب Histogram
        histogram = macd_line[-1] - signal_line[-1]
        
        return {
            'macd': macd_line[-1],
            'signal': signal_line[-1],
            'histogram': histogram
        }
    
    def analyze_market(self, symbol):
        """تحليل السوق لعملة معينة"""
        if not self.client:
            print("❌ Binance غير متصل")
            return
            
        print(f"\n📊 تحليل السوق: {symbol}")
        print("=" * 60)
        
        # السعر الحالي
        current_price = self.get_current_price(symbol)
        if current_price:
            print(f"💰 السعر الحالي: {current_price:,.4f} USDT")
        
        # السعر المفصل
        detailed_price = self.get_detailed_price(symbol)
        if detailed_price:
            print(f"\n📊 معلومات السعر المفصلة:")
            print("-" * 40)
            print(f"📈 أعلى (24س): {detailed_price['high_24h']:,.2f} USDT")
            print(f"📉 أقل (24س):  {detailed_price['low_24h']:,.2f} USDT")
            print(f"📊 الفتح (24س): {detailed_price['open_price_24h']:,.2f} USDT")
            print(f"📊 الحجم (24س): {detailed_price['volume_24h']:,.2f}")
            print(f"💰 قيمة التداول: {detailed_price['quote_volume_24h']:,.2f} USDT")
            print(f"📈 أعلى عرض شراء: {detailed_price['bid_price']:,.2f} USDT")
            print(f"📉 أقل عرض بيع: {detailed_price['ask_price']:,.2f} USDT")
            print(f"📏 الفرق (Spread): {detailed_price['spread']:,.2f} USDT")
        
        # شمعات 4 ساعات
        candles = self.get_4h_candles(symbol, 4)
        if candles:
            print(f"\n📈 بيانات الشارت - شمعات 4 ساعات:")
            print("=" * 60)
            
            for i, candle in enumerate(candles, 1):
                # تحويل الوقت إلى تاريخ مقروء
                from datetime import datetime
                candle_time = datetime.fromtimestamp(candle['open_time'] / 1000)
                time_str = candle_time.strftime("%Y-%m-%d %H:%M")
                
                print(f"🕯️ شمعة {i} - {time_str}")
                print(f"   📊 الفتح:     {candle['open']:>12,.2f} USDT")
                print(f"   📈 الأعلى:    {candle['high']:>12,.2f} USDT")
                print(f"   📉 الأقل:     {candle['low']:>12,.2f} USDT")
                print(f"   🎯 الإغلاق:   {candle['close']:>12,.2f} USDT")
                print(f"   📊 الحجم:     {candle['volume']:>12,.2f}")
                
                # حساب التغير
                change = candle['close'] - candle['open']
                change_percent = (change / candle['open']) * 100
                change_symbol = "📈" if change >= 0 else "📉"
                
                print(f"   {change_symbol} التغير:    {change:>+12,.2f} ({change_percent:>+6.2f}%)")
                
                # حساب Body و Wick
                body_size = abs(change)
                body_percent = (body_size / candle['high']) * 100
                upper_wick = candle['high'] - max(candle['open'], candle['close'])
                lower_wick = min(candle['open'], candle['close']) - candle['low']
                
                print(f"   📏 حجم الجسم: {body_size:>12,.2f} ({body_percent:>6.2f}%)")
                print(f"   🔝 الفتيل العلوي: {upper_wick:>12,.2f}")
                print(f"   🔻 الفتيل السفلي: {lower_wick:>12,.2f}")
                
                # نوع الشمعة
                if change > 0:
                    print(f"   🟢 شمعة صاعدة (Bullish)")
                elif change < 0:
                    print(f"   🔴 شمعة هابطة (Bearish)")
                else:
                    print(f"   ⚪ شمعة محايدة (Doji)")
                
                print("-" * 50)
            
            # تحليل الاتجاه العام
            print(f"\n📊 تحليل الاتجاه العام:")
            print("-" * 30)
            
            # حساب المتوسط المتحرك البسيط
            closes = [candle['close'] for candle in candles]
            sma = sum(closes) / len(closes)
            print(f"📈 المتوسط المتحرك (4 شمعات): {sma:,.2f} USDT")
            
            # اتجاه السعر
            if current_price > sma:
                print(f"📈 السعر أعلى من المتوسط: اتجاه صاعد")
            else:
                print(f"📉 السعر أقل من المتوسط: اتجاه هابط")
            
            # حساب التقلب
            highs = [candle['high'] for candle in candles]
            lows = [candle['low'] for candle in candles]
            volatility = (max(highs) - min(lows)) / sma * 100
            print(f"📊 التقلب: {volatility:.2f}%")
            
            # حساب مؤشر القوة النسبية (RSI)
            rsi = self.calculate_rsi(closes)
            print(f"📊 RSI (14): {rsi:.2f}")
            
            # تحليل RSI
            if rsi > 70:
                print(f"   ⚠️ RSI مرتفع: احتمال انعكاس هابط")
            elif rsi < 30:
                print(f"   ⚠️ RSI منخفض: احتمال انعكاس صاعد")
            else:
                print(f"   ✅ RSI في النطاق الطبيعي")
            
            # حساب مؤشر MACD
            macd_data = self.calculate_macd(closes)
            print(f"📊 MACD: {macd_data['macd']:.2f}")
            print(f"📊 Signal: {macd_data['signal']:.2f}")
            print(f"📊 Histogram: {macd_data['histogram']:.2f}")
            
            # تحليل MACD
            if macd_data['histogram'] > 0:
                print(f"   📈 MACD إيجابي: زخم صاعد")
            else:
                print(f"   📉 MACD سلبي: زخم هابط")
            
        else:
            print("❌ لا يمكن جلب بيانات الشمعات")
        
        print("=" * 60)
    
    async def show_last_3_days_messages(self):
        print("\n📅 رسائل آخر 3 أيام:")
        print("=" * 50)
        
        # تحديد بداية آخر 3 أيام (UTC)
        utc_now = datetime.now(pytz.UTC)
        three_days_ago = utc_now - timedelta(days=3)
        
        for channel_id in self.monitored_groups:
            try:
                entity = await self.client.get_entity(channel_id)
                print(f"\n📺 رسائل قناة: {entity.title}")
                
                # جلب جميع الرسائل من آخر 3 أيام
                messages = []
                async for message in self.client.iter_messages(entity, limit=2000):
                    # تحويل تاريخ الرسالة إلى UTC إذا لم يكن كذلك
                    message_date = message.date
                    if message_date.tzinfo is None:
                        message_date = pytz.UTC.localize(message_date)
                    
                    # فلترة رسائل آخر 3 أيام فقط
                    if message_date >= three_days_ago and message.text:
                        messages.append(message)
                
                # ترتيب الرسائل من الأقدم إلى الأحدث
                messages.sort(key=lambda x: x.date)
                
                if messages:
                    print(f"✅ تم العثور على {len(messages)} رسالة من آخر 3 أيام")
                    print("=" * 50)
                    
                    for message in messages:
                        sender = await message.get_sender()
                        sender_name = self.get_sender_name(sender)
                        timestamp = message.date.strftime("%Y-%m-%d %H:%M:%S")
                        
                        print(f"👤 {sender_name} | ⏰ {timestamp}")
                        print(f"📝 {message.text}")
                        print("-" * 30)
                else:
                    print("⚠️ لا توجد رسائل من آخر 3 أيام")
                    
            except Exception as e:
                print(f"❌ خطأ في جلب رسائل القناة {channel_id}: {e}")

async def main():
    monitor = TelegramMonitor()
    await monitor.start()

if __name__ == "__main__":
    asyncio.run(main())
